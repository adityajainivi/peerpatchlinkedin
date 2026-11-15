// Read-only scripts that run inside the LinkedIn page. Python calls them through browser.run_extract.
// Nothing here clicks, types or sends anything.

function peerpatchText(el, keepLines) {
  if (!el) return "";
  const copy = el.cloneNode(true);
  copy.querySelectorAll("button, .visually-hidden, script, style, svg, .update-components-actor__supplementary-actor-info")
    .forEach((n) => n.remove());
  if (keepLines) {
    copy.querySelectorAll("br").forEach((br) => br.replaceWith("\n"));
    copy.querySelectorAll("p, li, div").forEach((block) => block.append("\n"));
    return (copy.textContent || "")
      .replace(/[ \t ]+/g, " ")
      .replace(/ *\n */g, "\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }
  return (copy.textContent || "").replace(/\s+/g, " ").trim();
}

function peerpatchCount(text) {
  const m = (text || "").replace(/,/g, "").match(/(\d+(?:\.\d+)?)\s*([KkMm])?/);
  if (!m) return 0;
  let n = parseFloat(m[1]);
  if (m[2]) n *= m[2].toLowerCase() === "k" ? 1000 : 1000000;
  return Math.round(n);
}

function peerpatchPick(root, selectors) {
  for (const s of selectors) {
    const el = root.querySelector(s);
    if (el) return el;
  }
  return null;
}

function peerpatchCleanUrl(href) {
  if (!href) return "";
  try {
    const u = new URL(href, location.href);
    return u.origin + u.pathname;
  } catch (e) {
    return "";
  }
}

function peerpatchExtractPosts() {
  const exact = /^urn:li:(?:activity|share|ugcPost):\d{15,20}$/;
  const loose = /urn:li:(?:activity|share|ugcPost):\d{15,20}/;
  const found = new Map(); // urn -> container element

  for (const el of document.querySelectorAll("[data-urn], [data-chameleon-result-urn], [data-id]")) {
    if ([...found.values()].some((box) => box !== el && box.contains(el))) continue;
    for (const name of ["data-urn", "data-chameleon-result-urn", "data-id"]) {
      const value = el.getAttribute(name);
      if (value && exact.test(value)) {
        if (!found.has(value)) found.set(value, el);
        break;
      }
    }
  }

  const linkSelector = 'a[href*="urn:li:activity:"], a[href*="urn:li:ugcPost:"], a[href*="urn:li:share:"], a[href*="urn%3Ali%3A"]';
  for (const a of document.querySelectorAll(linkSelector)) {
    if ([...found.values()].some((box) => box.contains(a))) continue;
    let href = a.getAttribute("href") || "";
    try { href = decodeURIComponent(href); } catch (e) { /* keep raw */ }
    const m = href.match(loose);
    if (!m || found.has(m[0])) continue;
    const box = a.closest('[role="article"], article, li') || a.parentElement;
    if (box) found.set(m[0], box);
  }

  const posts = [];
  for (const [urn, box] of found) {
    const actorLink = peerpatchPick(box, [
      "a.update-components-actor__meta-link", "a.update-components-actor__image",
      'a[href*="/in/"]', 'a[href*="/company/"]', 'a[href*="/school/"]',
    ]);
    let author = peerpatchText(peerpatchPick(box, [".update-components-actor__title", ".update-components-actor__name"]));
    if (!author && actorLink) author = peerpatchText(actorLink).slice(0, 100);
    author = author.replace(/\s*[•·]\s*(?:1st|2nd|3rd\+?|Following)\s*$/i, "").trim();

    let textEl = peerpatchPick(box, [
      ".update-components-text", ".feed-shared-inline-show-more-text", ".feed-shared-text", '[class*="commentary"]',
    ]);
    if (!textEl) {
      let bestLen = 0;
      for (const el of box.querySelectorAll('span[dir="ltr"], p')) {
        const len = (el.textContent || "").trim().length;
        if (len > bestLen) { textEl = el; bestLen = len; }
      }
    }

    let reactions = 0;
    let comments = 0;
    const reactionCount = box.querySelector(".social-details-social-counts__reactions-count");
    if (reactionCount) reactions = peerpatchCount(reactionCount.textContent);
    for (const el of box.querySelectorAll("[aria-label]")) {
      const label = el.getAttribute("aria-label") || "";
      const r = label.match(/^([\d.,]+[KkMm]?)\s+reactions?\b/i);
      const c = label.match(/^([\d.,]+[KkMm]?)\s+comments?\b/i);
      if (r && !reactions) reactions = peerpatchCount(r[1]);
      if (c && !comments) comments = peerpatchCount(c[1]);
    }

    posts.push({
      urn,
      author,
      author_headline: peerpatchText(peerpatchPick(box, [".update-components-actor__description"])),
      author_url: actorLink ? peerpatchCleanUrl(actorLink.href) : "",
      time_label: peerpatchText(peerpatchPick(box, [".update-components-actor__sub-description"])),
      text: peerpatchText(textEl, true),
      reactions,
      comments,
    });
  }
  return posts;
}

function peerpatchExtractJobs() {
  const jobs = [];
  const seen = new Set();
  const cards = document.querySelectorAll('[data-entity-urn^="urn:li:jobPosting:"], .base-search-card, .job-search-card');
  for (const card of cards) {
    const holder = card.closest('[data-entity-urn^="urn:li:jobPosting:"]') || card.querySelector('[data-entity-urn^="urn:li:jobPosting:"]');
    const link = card.matches("a") ? card : card.querySelector('a.base-card__full-link, a[href*="/jobs/view/"]');
    let id = "";
    const urnMatch = ((holder && holder.getAttribute("data-entity-urn")) || "").match(/urn:li:jobPosting:(\d+)/);
    if (urnMatch) id = urnMatch[1];
    if (!id && link) {
      const hrefMatch = (link.getAttribute("href") || "").match(/\/jobs\/view\/(?:[^/?#]*?-)?(\d{6,})/);
      if (hrefMatch) id = hrefMatch[1];
    }
    if (!id || seen.has(id)) continue;
    seen.add(id);

    const read = (selector) => peerpatchText(card.querySelector(selector));
    const time = card.querySelector("time");
    const companyLink = card.querySelector(".base-search-card__subtitle a");
    jobs.push({
      job_id: id,
      title: read(".base-search-card__title") || peerpatchText(link),
      company: read(".base-search-card__subtitle"),
      company_url: companyLink ? peerpatchCleanUrl(companyLink.href) : "",
      location: read(".job-search-card__location"),
      posted_date: time ? time.getAttribute("datetime") || "" : "",
      posted_label: peerpatchText(time),
      salary: read(".job-search-card__salary-info"),
      benefit: read(".job-posting-benefits__text"),
    });
  }
  return jobs;
}

function peerpatchScrollToBottom() {
  window.scrollTo(0, document.documentElement.scrollHeight);
  for (const el of document.querySelectorAll("main, .scaffold-layout__main, .scaffold-finite-scroll, #workspace")) {
    if (el.scrollHeight > el.clientHeight + 10) el.scrollTop = el.scrollHeight;
  }
  return document.documentElement.scrollHeight;
}
