#!/usr/bin/env python3

import logging
import sys
import csv
import re
from urllib.parse import parse_qs, urlparse
import sqlite3
import subprocess
import shlex
from pathlib import Path

from requests_cache import CachedSession
import lxml.html
import click

SITE_URL = "http://www.cdep.ro"
ROOT_URL = "/pls/proiecte/upl_pck2015.home"
PDF_ROOT = Path("/app/pdfs")

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

UA = (
    "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) "
    "Gecko/20100101 Firefox/89.0"
)

class ValueCache:

    def __init__(self, path):
        self.con = sqlite3.connect(path, isolation_level=None)
        self.con.execute("""
            create table if not exists cache
            (id text primary key, value text);
        """)

    def save(self, key, value):
        res = self.con.execute(
            "insert into cache(id, value) values(?, ?)",
            (key, value),
        )

    def get(self, key):
        res = self.con.execute(
            "select value from cache where id = ?",
            (key,),
        )
        rows = res.fetchall()
        if rows:
            return rows[0][0]
        else:
            raise KeyError


pagecount_cache = ValueCache("/var/local/requests_cache/pagecount.db")


def resolve(url):
    return f"{SITE_URL}{url}"


def get(url):
    logger.debug("GET %s", url)
    return lxml.html.fromstring(session.get(resolve(url)).text)


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


def count_pages(url):
    rel_path = urlparse(url).path.lstrip("/")

    try:
        return rel_path, pagecount_cache.get(url)
    except KeyError:
        pass

    logger.debug("Counting pages %s", url)

    path = PDF_ROOT / rel_path
    path.parent.mkdir(exist_ok=True, parents=True)
    q = lambda arg: shlex.quote(str(arg))

    download_cmd = f"curl -s {q(url)} -H '{UA}' -o {q(path)}"
    pages_cmd = f"pdfinfo {q(path)}"

    try:
        if not path.exists():
            subprocess.check_call(download_cmd, shell=True)
        res = subprocess.check_output(pages_cmd, shell=True).decode("utf8")

    except Exception:
        pages = -1
        try:
            path.unlink()
        except:
            pass

    else:
        pages = int(re.search(r"Pages:\s+(\d+)\s", res).group(1))

    pagecount_cache.save(url, pages)
    return rel_path, pages


def bill_page(url):
    page = get(url).cssselect(".program-lucru-detalii")[0]

    idp = parse_qs(url.split("?", 1)[1])["idp"][0]
    title = page.cssselect("h1")[0].text
    description = page.cssselect("h4")[0].text
    fields = {
        "idp": idp,
        "Title": title,
        "Description": description,
        "url_cdep": resolve(url),
        "pages_forma_initiatorului": "",
        "pages_forma_senat": "",
        "pdf": "",
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

                sponsor_count = int(number_match.group("number"))
                fields["sponsor_count"] = sponsor_count

                for itr in tds[1].cssselect("tr"):
                    itds = itr.cssselect("td")
                    affiliation = itds[0].text.replace(":", "")
                    for a in itds[1].cssselect("a"):
                        href = a.attrib["href"]
                        sponsors.append({
                            "name": a.text,
                            "affiliation": affiliation,
                            "url": resolve(href),
                        })

    pdf_links = {}
    for pdf_link in page.cssselect("a[target=PDF]"):
        tr = pdf_link.getparent().getparent()
        label = tr.text_content().strip()
        pdf_links[label] = pdf_link.attrib["href"]

    try:
        href = pdf_links["Forma iniţiatorului"]
    except KeyError:
        pass
    else:
        rel_path, pages = count_pages(resolve(href))
        fields["pdf"] = rel_path
        fields["pages_forma_initiatorului"] = pages

    try:
        href = pdf_links["Forma adoptată de Senat"]
    except KeyError:
        pass
    else:
        rel_path, pages = count_pages(resolve(href))
        fields["pdf"] = rel_path
        fields["pages_forma_senat"] = pages

    return fields, sponsors


def iter_bills():
    errors = 0
    try:
        for year_url in years():
            for bill_url in bills(year_url):
                try:
                    yield bill_page(bill_url)
                except Exception:
                    logger.exception("Failed to parse %s", bill_url)
                    errors += 1
    finally:
        logger.info("Error count: %d", errors)


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
        "pages_forma_initiatorului",
        "pages_forma_senat",
        "pdf",
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
