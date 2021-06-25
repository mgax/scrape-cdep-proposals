#!/usr/bin/env python3

import logging
import sys
import csv
from urllib.parse import parse_qs

from requests_cache import CachedSession
import lxml.html
import click

SITE_URL = "http://www.cdep.ro"
ROOT_URL = "/pls/proiecte/upl_pck2015.home"

session = CachedSession(cache_name="/var/local/requests_cache/cache.db")

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

OK_FIELDS = [
    "B.P.I.",
    "Camera Deputatilor",
    "Senat",
    "Guvern",
    "Procedura legislativa",
    "Camera decizionala",
    "Tip initiativa",
    "Caracter",
    "Procedura de urgenta",
    "Stadiu",
    "Initiator",
    "Prioritate legislativa",
    "Consultare publica",
]


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
    page = get(url).cssselect(".program-lucru-detalii")[0]

    idp = parse_qs(url.split("?", 1)[1])["idp"][0]
    title = page.cssselect("h1")[0].text
    description = page.cssselect("h4")[0].text
    rv = {
        "idp": idp,
        "Title": title,
        "Description": description,
        "URL CDEP": f"{SITE_URL}{url}",
    }

    tbody = page.cssselect("table tbody")[0]
    for tr in tbody.cssselect(":scope > tr"):
        tds = tr.cssselect(":scope > td")
        if len(tds) >= 2:
            name = tds[0].text.replace("-", "").replace(":", "").strip()
            if name in OK_FIELDS:
                value = tds[1].text_content().strip()
                rv[name] = value

    return rv


def iter_proposals():
    for year_url in years():
        for proposal_url in proposals(year_url):
            yield proposal_page(proposal_url)


@click.command()
@click.argument("out_file", type=click.File(mode="w"))
def scrape(out_file):
    fieldnames = [
        "idp",
        "Title",
        "Description",
        "URL CDEP",
    ] + OK_FIELDS
    writer = csv.DictWriter(out_file, fieldnames=fieldnames)
    writer.writeheader()
    for proposal in iter_proposals():
        writer.writerow(proposal)


if __name__ == "__main__":
    logging.basicConfig()
    scrape()
