#!/usr/bin/env python3

import logging

from requests_cache import CachedSession
import lxml.html

SITE_URL = "http://www.cdep.ro"
ROOT_URL = "/pls/proiecte/upl_pck2015.home"

session = CachedSession(cache_name="/var/local/requests_cache/cache.db")

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def get(url):
    logger.debug("GET %s", url)
    return lxml.html.fromstring(session.get(f"{SITE_URL}{url}").text)


def years():
    for td in get(ROOT_URL).cssselect("td"):
        if not td.text:
            continue

        if td.text == "înregistrate la\nCamera Deputatilor\nîn anul:":
            for a in td.getnext().cssselect("a"):
                yield a.attrib["href"]


def proposals(url):
    for a in get(url).cssselect("tbody tr td:nth-child(2) a"):
        yield a.attrib["href"]


def proposal_page(url):
    for tr in get(url).cssselect("tbody tr"):
        if len(tr.cssselect("td")) >= 2:
            print(tr)
            break


def main():
    for year_url in years():
        for proposal_url in proposals(year_url):
            proposal_page(proposal_url)
            return


if __name__ == "__main__":
    logging.basicConfig()
    main()
