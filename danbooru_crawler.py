import os
import json
import time
import argparse
import httpx


class DanbooruCrawler:
    def __init__(
            self, 
            username,
            api_key,
            output_dir="danbooru_images", 
            tags=None, 
            start_page=1, 
            max_pages=10, 
            images_per_page=100,
        ):
        self.base_url = "https://danbooru.donmai.us/posts.json"
        self.username = username
        self.api_key = api_key
        self.output_dir = output_dir
        self.metadata_path = os.path.join(output_dir, "metadata")
        self.tags = set(tags or [])
        self.start_page = start_page
        self.max_pages = max_pages
        self.images_per_page = min(images_per_page, 200)

        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.metadata_path, exist_ok=True)

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Referer": "https://danbooru.donmai.us"
        }

        self.metadata = []

    def fetch_posts(self, client, page):
        time.sleep(2)
        params = {
            "page": page,
            "limit": self.images_per_page,
            "login": self.username,
            "api_key": self.api_key
        }
        if self.tags:
            params["tag_string"] = " ".join(self.tags)

        try:
            response = client.get(self.base_url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"[ERROR] Failed to fetch page {page}: {e}")
            return []

    def download_image(self, client, url, save_path):
        try:
            response = client.get(url)
            response.raise_for_status()
            with open(save_path, "wb") as f:
                f.write(response.content)
            return True
        except Exception as e:
            print(f"[ERROR] Failed to download image: {e}")
            return False

    def crawl(self):
        print(f"Start crawling Danbooru (start page: {self.start_page}, per page: {self.images_per_page})")
        image_id_set = set()

        with httpx.Client(http2=True, headers=self.headers, timeout=30.0) as client:
            empty_post_cnt = 0
            for page in range(self.start_page, self.max_pages + 1):
                print(f'crawling tags: {self.tags}, page: {page}')
                posts = self.fetch_posts(client, page)

                if not posts:
                    empty_post_cnt += 1
                    print(f"[INFO] Empty post count: {empty_post_cnt}")
                    if empty_post_cnt >= 3:
                        print(f"[INFO] No more posts returned at page {page}, stopping early.")
                        break
                    else:
                        continue
                else:
                    empty_post_cnt = 0

                for post in posts:
                    if not post.get("file_url"):
                        continue

                    post_tags = set(post.get('tag_string', '').lower().split())
                    if self.tags and not self.tags & post_tags:
                        continue

                    image_id = post["id"]
                    if image_id in image_id_set:
                        continue
                    image_id_set.add(image_id)

                    image_url = f"https://danbooru.donmai.us{post['file_url']}" if post["file_url"].startswith("/") else post["file_url"]
                    image_ext = os.path.splitext(image_url)[-1]

                    if image_ext not in {".jpg", ".jpeg", ".png", ".webp"}:
                        continue

                    filename = f"{image_id}{image_ext}"
                    save_path = os.path.join(self.output_dir, filename)

                    success = self.download_image(client, image_url, save_path)
                    if not success:
                        continue
                    
                    tags = clean_tags(post.get("tag_string", ""))
                    if post.get("rating") == "e":
                        tags.insert(0, "R-18")

                    metadata = {
                        "id": image_id,
                        "file_name": filename,
                        "width": post.get("image_width"),
                        "height": post.get("image_height"),
                        "tags": tags,
                        "rating": post.get("rating"),
                        "source": post.get("source"),
                        "score": post.get("score")
                    }

                    self.metadata.append(metadata)

                    with open(os.path.join(self.metadata_path, f"{image_id}.json"), "w", encoding="utf-8") as f:
                        json.dump(metadata, f, ensure_ascii=False, indent=2)

        print(f"Download complete: {len(self.metadata)} images saved to '{self.output_dir}'")


def clean_tags(raw_tag_string):
    tags = raw_tag_string.split()
    return [tag for tag in tags if tag.isalnum() or len(tag) > 1]

def main():
    parser = argparse.ArgumentParser(description="Danbooru Image Crawler (httpx)")
    parser.add_argument("--username", type=str, required=True, help="username")
    parser.add_argument("--api-key", type=str, required=True, help="api key")
    parser.add_argument("--output-dir", default="danbooru_images", help="Directory to save images and metadata")
    parser.add_argument("--start-page", type=int, default=1, help="Number of pages to start")
    parser.add_argument("--end-page", type=int, default=1000000, help="Number of pages to end")
    parser.add_argument("--limit", type=int, default=200, help="Images per page (max 200)")
    parser.add_argument("--tags", nargs="+", help="List of tags to filter by (space-separated)")
    args = parser.parse_args()

    crawler = DanbooruCrawler(
        username=args.username,
        api_key=args.api_key,
        output_dir=args.output_dir,
        tags=args.tags, 
        start_page=args.start_page, 
        max_pages=args.end_page, 
        images_per_page=args.limit
    )
    crawler.crawl()

if __name__ == "__main__":
    main()
