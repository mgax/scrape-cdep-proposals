#!/usr/bin/env python3

import logging
import sys
import csv
import re
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


def bills(url):
    for a in get(url).cssselect("tbody tr td:nth-child(2) a"):
        yield a.attrib["href"]


def bill_page(url):
    page = get(url).cssselect(".program-lucru-detalii")[0]

    idp = parse_qs(url.split("?", 1)[1])["idp"][0]
    title = page.cssselect("h1")[0].text
    description = page.cssselect("h4")[0].text
    fields = {
        "idp": idp,
        "Title": title,
        "Description": description,
        "url_cdep": f"{SITE_URL}{url}",
    }

    sponsors = []

    tbody = page.cssselect("table tbody")[0]
    for tr in tbody.cssselect(":scope > tr"):
        tds = tr.cssselect(":scope > td")
        if len(tds) >= 2:
            name = tds[0].text.replace("-", "").replace(":", "").strip()

            if name in OK_FIELDS:
                value = tds[1].text_content().strip()
                fields[name] = value

            if name == "Initiator" and tds[1].cssselect("table"):
                number_match = re.match(r"(?P<number>\d+)\s", tds[1].text)
                assert number_match, f"Failed to parse `Initiator` in {url}"

                fields["sponsor_count"] = int(number_match.group("number"))

                for itr in tds[1].cssselect("tr"):
                    itds = itr.cssselect("td")
                    affiliation = itds[0].text.replace(":", "")
                    for a in itds[1].cssselect("a"):
                        href = a.attrib["href"]
                        sponsors.append({
                            "name": a.text,
                            "affiliation": affiliation,
                            "url": f"{SITE_URL}{href}",
                        })

    return fields, sponsors


def iter_bills():
    for year_url in years():
        for bill_url in bills(year_url):
            try:
                yield bill_page(bill_url)
            except Exception:
                logger.exception("Failed to parse %s", bill_url)


@click.command()
@click.argument("bills_csv", type=click.File(mode="w"))
@click.argument("sponsors_csv", type=click.File(mode="w"))
def scrape(bills_csv, sponsors_csv):
    bill_fields = [
        "idp",
        "Title",
        "Description",
        "url_cdep",
        "sponsor_count",
    ] + OK_FIELDS
    bills_writer = csv.DictWriter(bills_csv, fieldnames=bill_fields)
    bills_writer.writeheader()

    sponsor_fields = ["idp", "name", "affiliation", "url"]
    sponsors_writer = csv.DictWriter(sponsors_csv, fieldnames=sponsor_fields)
    sponsors_writer.writeheader()

    for fields, sponsors in iter_bills():
        bills_writer.writerow(fields)

        for sponsor in sponsors:
            sponsors_writer.writerow(dict(sponsor, idp=fields["idp"]))


if __name__ == "__main__":
    logging.basicConfig()
    scrape()
