import os
import json
import time
import argparse
import requests
from tqdm import tqdm
from pathlib import Path


class PixivRankingCrawler:
    def __init__(self, cookie_file, output_dir="ranking_images", mode="daily", date=None):
        self.cookies = self.load_cookie(cookie_file)
        self.output_dir = output_dir
        self.metadata_dir = os.path.join(output_dir, "metadata")
        self.mode = mode
        self.date = date
        self.session = self.create_session()
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.metadata_dir, exist_ok=True)

    def load_cookie(self, path):
        with open(path, 'r') as f:
            return f.readline().strip()

    def create_session(self):
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Referer': 'https://www.pixiv.net/ranking.php?mode=daily',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8'
        })
        session.cookies.set('PHPSESSID', self.cookies, domain='.pixiv.net')
        return session

    def get_illust_ids(self, page=1):
        url = "https://www.pixiv.net/ranking.php"
        params = {
            "mode": self.mode,
            "p": page,
            "format": "json"
        }
        if self.date:
            params["date"] = self.date.replace('-', '')  # YYYYMMDD

        print(f"[DEBUG] GET {url} page={page}")
        resp = self.session.get(url, params=params)
        print(f"[DEBUG] status_code: {resp.status_code}")
        resp.raise_for_status()

        data = resp.json()
        contents = data.get("contents", [])
        illust_ids = [str(item["illust_id"]) for item in contents if "illust_id" in item]

        print(f"[DEBUG] Found {len(illust_ids)} illust IDs from JSON API")
        return illust_ids

    def get_image_detail(self, illust_id):
        url = f"https://www.pixiv.net/ajax/illust/{illust_id}"
        resp = self.session.get(url)
        resp.raise_for_status()
        data = resp.json()

        if data.get("error"):
            return None, None

        info = data["body"]
        image_url = info.get("urls", {}).get("original")
        if not image_url:
            return None, None

        metadata = {
            "id": illust_id,
            "title": info.get("title", ""),
            "tags": [tag["tag"] for tag in info.get("tags", {}).get("tags", [])],
            "user_name": info.get("userName", ""),
            "create_date": info.get("createDate", ""),
            "bookmark_count": info.get("bookmarkCount", 0),
            "like_count": info.get("likeCount", 0),
            "view_count": info.get("viewCount", 0),
            "url": image_url
        }

        return image_url, metadata

    def download_image(self, url, illust_id, metadata):
        try:
            filename = f"{illust_id}.jpg"
            filepath = os.path.join(self.output_dir, filename)

            if os.path.exists(filepath):
                return False

            headers = {'Referer': 'https://www.pixiv.net/'}
            resp = self.session.get(url, headers=headers, stream=True)
            resp.raise_for_status()

            with open(filepath, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            metadata_path = Path(self.metadata_dir) / f"{illust_id}.json"
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)

            return True

        except Exception as e:
            print(f"[ERROR] Download failed for {url}: {e}")
            return False

    def run(self, max_images=100):
        count = 0
        page = 1

        with tqdm(total=max_images, desc=f"Pixiv Ranking [{self.mode}]") as pbar:
            while count < max_images:
                try:
                    illust_ids = self.get_illust_ids(page)
                    if not illust_ids:
                        break

                    for illust_id in illust_ids:
                        if count >= max_images:
                            break

                        image_url, metadata = self.get_image_detail(illust_id)
                        if not image_url:
                            continue

                        if self.download_image(image_url, illust_id, metadata):
                            count += 1
                            pbar.update(1)

                        time.sleep(2)

                    page += 1
                    time.sleep(3)

                except Exception as e:
                    print(f"[ERROR] page {page}: {e}")
                    page += 1
                    time.sleep(5)

        print(f"[DONE] Downloaded {count} images.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cookie_file", required=True, help="Text file with PHPSESSID in first line")
    parser.add_argument("--output_dir", default="ranking_images")
    parser.add_argument("--mode", choices=["daily", "weekly", "monthly", "rookie", "male", "female",
                                           "daily_r18", "weekly_r18", "male_r18", "female_r18"], default="daily")
    parser.add_argument("--date", help="Specific date in YYYY-MM-DD (optional)")
    parser.add_argument("--max_images", type=int, default=100)
    args = parser.parse_args()

    crawler = PixivRankingCrawler(args.cookie_file, args.output_dir, args.mode, args.date)
    crawler.run(args.max_images)
