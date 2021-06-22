#!/usr/bin/env python3

from requests_cache import CachedSession
import lxml.html

ROOT_URL = "http://www.cdep.ro/pls/proiecte/upl_pck2015.home"

session = CachedSession(cache_name="/var/local/requests_cache/cache.db")


def main():
    root = lxml.html.fromstring(session.get(ROOT_URL).text)

    for td in root.cssselect("td"):
        if not td.text:
            continue

        if td.text == "înregistrate la\nCamera Deputatilor\nîn anul:":
            for a in td.getnext().cssselect("a"):
                print(a.text)


if __name__ == "__main__":
    main()
