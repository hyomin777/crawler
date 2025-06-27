import time
import argparse
import requests
from pathlib import Path


class Crawler:
    def __init__(self, query, per_page, start_page, max_page, access_key):
        self.query = query
        self.per_page = per_page
        self.start_page = start_page
        self.max_page = max_page

        self.save_dir = Path(f"./data/{query}")
        self.save_dir.mkdir(parents=True, exist_ok=True)

        self.headers = {
            "Accept-Version": "v1",
            "Authorization": f"Client-ID {access_key}"
        }

    def download_image(self, url, filepath):
        try:
            img_data = requests.get(url).content
            with open(filepath, 'wb') as f:
                f.write(img_data)
        except Exception as e:
            print(f"Download failed: {e}")

    def crawl(self):
        for page in range(self.start_page, self.max_page + 1):
            print(f"[Query: {self.query}] Page: {page} Fetching...")

            params = {
                "query": self.query,
                "page": page,
                "per_page": self.per_page
            }
            r = requests.get("https://api.unsplash.com/search/photos", headers=self.headers, params=params)

            if r.status_code == 200:
                data = r.json()
                results = data.get("results", [])

                print(f'Total: {data.get("total")} | Total Pages: {data.get("total_pages")}')
                if not results:
                    break
                if data.get("total_pages", self.max_page) < page:
                    break

                for i, item in enumerate(data.get("results", [])):
                    img_url = item["urls"]["regular"]
                    img_id = item["id"]
                    filepath = self.save_dir / f"{img_id}.jpg"

                    if not filepath.exists():
                        self.download_image(img_url, filepath)

                time.sleep(90)

            else:
                print(f'[Status Code:{r.status_code}] Waiting for 1 hour')
                time.sleep(60*60)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", type=str, required=True)
    parser.add_argument("--access-key", type=str, required=True)
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--max-page", type=int, default=1000)
    parser.add_argument("--per-page", type=int, default=30)
    args = parser.parse_args()

    crawler = Crawler(
        args.query,
        args.per_page,
        args.start_page,
        args.max_page,
        args.access_key
    )
    crawler.crawl()


if __name__ == '__main__':
    main()