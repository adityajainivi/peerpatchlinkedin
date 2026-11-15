"""HTML shaped like LinkedIn's pages, with the content swapped for test data."""
from __future__ import annotations

import html
from datetime import datetime


def urn_for(when: datetime, kind: str = "activity", salt: int = 12345) -> str:
    """Build a post URN whose top 41 bits hold `when`, the way LinkedIn's do."""
    ms = round(when.timestamp() * 1000)
    return f"urn:li:{kind}:{(ms << 22) | (salt & 0x3FFFFF)}"


def _e(text: str) -> str:
    return html.escape(text or "")


def _text_html(text: str) -> str:
    return _e(text).replace("\n", "<br>")


def post_standard(urn, author, headline, profile_url, time_label, text, reactions, comments):
    """A post card as it appears in LinkedIn post search results."""
    profile = f"{profile_url}?miniProfileUrn=urn%3Ali%3Afs_miniProfile%3AACoAAB"
    return f"""
<li class="artdeco-card mb2">
  <div data-chameleon-result-urn="{urn}">
    <div class="feed-shared-update-v2 feed-shared-update-v2--minimal-padding full-height relative artdeco-card" data-urn="{urn}" role="article">
      <div class="update-components-actor display-flex">
        <a class="update-components-actor__image relative" href="{profile}"><img alt="View {_e(author)}'s profile" src="data:,"></a>
        <div class="update-components-actor__container">
          <a class="update-components-actor__meta-link" href="{profile}">
            <span class="update-components-actor__title">
              <span class="hoverable-link-text t-14 t-bold"><span dir="ltr"><span aria-hidden="true"><!---->{_e(author)}<!----></span><span class="visually-hidden"><!---->View {_e(author)}'s profile<!----></span></span></span>
            </span>
            <span class="update-components-actor__description text-body-xsmall t-black--light">
              <span aria-hidden="true"><!---->{_e(headline)}<!----></span><span class="visually-hidden"><!---->{_e(headline)}<!----></span>
            </span>
            <span class="update-components-actor__sub-description text-body-xsmall t-black--light">
              <span aria-hidden="true"><!---->{_e(time_label)} • <!----><svg></svg></span><span class="visually-hidden"><!---->{_e(time_label)} ago • Visible to anyone on or off LinkedIn<!----></span>
            </span>
          </a>
        </div>
      </div>
      <div class="feed-shared-update-v2__description-wrapper mr2">
        <div class="feed-shared-inline-show-more-text feed-shared-update-v2__description" tabindex="-1">
          <div class="update-components-text relative update-components-update-v2__commentary" dir="ltr">
            <span class="break-words tvm-parent-container"><span dir="ltr">{_text_html(text)}</span></span>
          </div>
          <button class="feed-shared-inline-show-more-text__see-more-less-toggle see-more t-14" type="button"><span>…more</span></button>
        </div>
      </div>
      <div class="social-details-social-counts">
        <ul class="display-flex">
          <li class="social-details-social-counts__item social-details-social-counts__reactions">
            <button aria-label="{reactions:,} reactions" type="button"><span aria-hidden="true" class="social-details-social-counts__reactions-count">{reactions:,}</span></button>
          </li>
          <li class="social-details-social-counts__item social-details-social-counts__comments">
            <button aria-label="{comments} comments on {_e(author)}'s post" type="button"><span aria-hidden="true">{comments} comments</span></button>
          </li>
        </ul>
      </div>
      <article class="comments-comment-entity" data-id="urn:li:comment:({urn},7400000000000000001)">
        <span dir="ltr">Interested! Sharing my CV.</span>
      </article>
    </div>
  </div>
</li>"""


def post_minimal(urn, company, company_url, text, reactions=0):
    """A stripped-down post card with none of the usual class names. Tests the fallbacks."""
    return f"""
<div role="article" data-id="{urn}">
  <div><a href="{company_url}"><span dir="ltr">{_e(company)}</span></a></div>
  <p><span dir="ltr">{_text_html(text)}</span></p>
  <button aria-label="{reactions} reactions">{reactions}</button>
</div>"""


def post_link_only(urn, author, profile_url, text):
    """A post whose ID only appears in its link. Tests the link fallback."""
    return f"""
<article>
  <a href="{profile_url}">{_e(author)}</a>
  <p>{_text_html(text)}</p>
  <a href="https://www.linkedin.com/feed/update/{urn}/">View post</a>
</article>"""


def search_page(cards, batch=3):
    """Post search results page. Shows `batch` cards, reveals the next batch each time you scroll to the bottom."""
    first = "".join(cards[:batch])
    later = "".join(
        '<template class="more">' + "".join(cards[i:i + batch]) + "</template>"
        for i in range(batch, len(cards), batch)
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Search | LinkedIn</title>
<style>li.artdeco-card, [role=article], article {{ display: block; min-height: 500px; }}</style></head>
<body><main class="scaffold-layout__main"><div class="search-results-container">
<ul class="reusable-search__entity-result-list list-style-none" id="results">{first}</ul>
</div></main>
{later}
<script>
function revealMore() {{
  if (window.innerHeight + window.scrollY < document.documentElement.scrollHeight - 50) return;
  var next = document.querySelector("template.more");
  if (!next) return;
  document.getElementById("results").appendChild(next.content.cloneNode(true));
  next.remove();
}}
window.addEventListener("scroll", revealMore);
window.addEventListener("wheel", function () {{ setTimeout(revealMore, 0); }});
</script>
</body></html>"""


def job_card(job_id, title, company, company_slug, location, date, label, salary="", benefit=""):
    """A job card from LinkedIn's public job listing (div root with a full-card link)."""
    benefit_html = (
        '<div class="job-posting-benefits text-sm"><icon class="job-posting-benefits__icon"></icon>'
        f'<span class="job-posting-benefits__text">{_e(benefit)}</span></div>'
    ) if benefit else ""
    salary_html = f'<span class="job-search-card__salary-info">{_e(salary)}</span>' if salary else ""
    slug = title.lower().replace(" ", "-")
    return f"""
<li>
  <div class="base-card relative w-full hover:no-underline base-card--link base-search-card base-search-card--link job-search-card" data-entity-urn="urn:li:jobPosting:{job_id}" data-impression-id="jobs-search-result-0" data-tracking-id="xyz==">
    <a class="base-card__full-link absolute top-0 right-0 bottom-0 left-0 p-0 z-[2]" href="https://in.linkedin.com/jobs/view/{slug}-at-{company_slug}-{job_id}?position=1&amp;pageNum=0&amp;refId=abc&amp;trackingId=xyz" data-tracking-control-name="public_jobs_jserp-result_search-card">
      <span class="sr-only">
            {_e(title)}
      </span>
    </a>
    <div class="search-entity-media"><img class="artdeco-entity-image" alt="{_e(company)}" src="data:,"></div>
    <div class="base-search-card__info">
      <h3 class="base-search-card__title">
            {_e(title)}
      </h3>
      <h4 class="base-search-card__subtitle">
          <a class="hidden-nested-link" href="https://in.linkedin.com/company/{company_slug}?trk=public_jobs_jserp-result_job-search-card-subtitle">
            {_e(company)}
          </a>
      </h4>
      <div class="base-search-card__metadata">
          <span class="job-search-card__location">
            {_e(location)}
          </span>
          {benefit_html}
          {salary_html}
          <time class="job-search-card__listdate--new" datetime="{date}">
            {_e(label)}
          </time>
      </div>
    </div>
  </div>
</li>"""


def job_card_anchor(job_id, title, company, location, date, label):
    """The other public job card shape: the whole card is one <a>, and the company isn't linked."""
    return f"""
<li>
  <a class="base-card relative w-full base-card--link base-search-card base-search-card--link job-search-card" href="https://www.linkedin.com/jobs/view/{job_id}/?trk=public_jobs" data-entity-urn="urn:li:jobPosting:{job_id}">
    <div class="base-search-card__info">
      <h3 class="base-search-card__title">{_e(title)}</h3>
      <h4 class="base-search-card__subtitle">{_e(company)}</h4>
      <div class="base-search-card__metadata">
        <span class="job-search-card__location">{_e(location)}</span>
        <time class="job-search-card__listdate" datetime="{date}">{_e(label)}</time>
      </div>
    </div>
  </a>
</li>"""
