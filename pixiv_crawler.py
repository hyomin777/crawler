import os
import json
import time
import random
import argparse
import requests
from tqdm import tqdm
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class PixivCrawler:
    def __init__(self, cookie_file, output_dir="images"):
        self.cookie_file = cookie_file
        self.cookies = self.load_cookies()
        self.current_cookie_index = 0
        self.output_dir = output_dir
        self.metadata_dir = os.path.join(output_dir, "metadata")
        self.last_request_time = 0
        self.min_request_interval = 2.0  # Minimum seconds between requests
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(self.metadata_dir, exist_ok=True)
        self.session = self.create_session()

    def load_cookies(self):
        """Load cookies from file"""
        if not os.path.exists(self.cookie_file):
            raise FileNotFoundError(
                f"Cookie file {self.cookie_file} not found")

        with open(self.cookie_file, 'r') as f:
            cookies = [line.strip() for line in f if line.strip()]

        if not cookies:
            raise ValueError("No cookies found in the cookie file")

        return cookies

    def create_session(self):
        """Create a new session with current cookie"""
        session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=3,  # Maximum number of retries
            backoff_factor=1,  # Wait 1, 2, 4, 8, 16 seconds between retries
            # Retry on these status codes
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
            'Referer': 'https://www.pixiv.net/'
        })
        session.cookies.set(
            'PHPSESSID', self.cookies[self.current_cookie_index], domain='.pixiv.net')
        return session
    
    def rate_limit(self):
        """Enforce rate limiting between requests"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        if time_since_last_request < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last_request
            # Add some randomness
            time.sleep(sleep_time + random.uniform(0.1, 0.5))
        self.last_request_time = time.time()

    def rotate_cookie(self):
        """Rotate to next cookie"""
        self.current_cookie_index = (self.current_cookie_index + 1) % len(self.cookies)
        self.session = self.create_session()
        print(f"Rotated to cookie {self.current_cookie_index + 1}/{len(self.cookies)}")
        time.sleep(5)  # Wait after rotating cookie

    def save_metadata(self, illust_id, metadata):
        """Save image metadata to JSON file"""
        metadata_file = os.path.join(self.metadata_dir, f"{illust_id}.json")
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    def download_image(self, image_url, image_id, metadata, page_index=0):
        try:
            filename = f"{image_id}_p{page_index}.jpg"
            filepath = os.path.join(self.output_dir, filename)

            if os.path.exists(filepath):
                return False

            response = self.session.get(image_url, stream=True)
            response.raise_for_status()

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            metadata['filename'] = filename
            self.save_metadata(f"{image_id}_p{page_index}", metadata)

            return True

        except Exception as e:
            print(f"Error downloading {image_url}: {str(e)}")
            return False
    
    def get_image_details(self, illust_id, max_retries=3):
        """Get image details with retry logic (handles multi-page works)"""
        for attempt in range(max_retries):
            try:
                self.rate_limit()
                detail_url = f"https://www.pixiv.net/ajax/illust/{illust_id}/pages"
                response = self.session.get(detail_url)
                response.raise_for_status()
                pages = response.json()

                # Get illustration metadata
                self.rate_limit()
                meta_url = f"https://www.pixiv.net/ajax/illust/{illust_id}"
                meta_response = self.session.get(meta_url)
                meta_response.raise_for_status()
                meta_data = meta_response.json()

                if meta_data.get('error'):
                    print(f"Error getting metadata: {meta_data['error']['message']}")
                    return [], []

                meta_body = meta_data['body']
                base_metadata = {
                    'id': illust_id,
                    'title': meta_body.get('title', ''),
                    'user_id': meta_body.get('userId', ''),
                    'user_name': meta_body.get('userName', ''),
                    'tags': [tag['tag'] for tag in meta_body.get('tags', {}).get('tags', [])],
                    'create_date': meta_body.get('createDate', ''),
                    'width': meta_body.get('width', 0),
                    'height': meta_body.get('height', 0),
                    'page_count': meta_body.get('pageCount', 1),
                    'bookmark_count': meta_body.get('bookmarkCount', 0),
                    'like_count': meta_body.get('likeCount', 0),
                    'view_count': meta_body.get('viewCount', 0),
                    'comment_count': meta_body.get('commentCount', 0),
                    'is_original': meta_body.get('isOriginal', False),
                    'is_r18': meta_body.get('xRestrict', 0) > 0,
                }

                image_urls = []
                metadata_list = []

                for i, page in enumerate(pages.get('body', [])):
                    image_url = page.get('urls', {}).get('original', '')
                    if not image_url:
                        continue
                    image_urls.append(image_url)

                    meta_copy = dict(base_metadata)
                    meta_copy['page'] = i
                    metadata_list.append(meta_copy)

                return image_urls, metadata_list

            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    print(f"Retrying in {wait_time:.1f} seconds... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    if "429" in str(e):
                        self.rotate_cookie()
                else:
                    print(f"Failed to get image details after {max_retries} attempts: {str(e)}")
                    return [], []

        return [], []

    def search_and_download(self, tags, max_images, mode='s_tag', rating='all'):
        """
        Search and download images by tags

        Args:
            tags (list): List of tags to search for
            max_images (int): Maximum number of images to download
            days (int): Number of days to look back
            mode (str): Search mode
                - 's_tag': Any tag can match
                - 's_tag_full': All tags must match
            rating (str): Content rating
                - 'all': All ratings
                - 'safe': Safe for work
                - 'r18': R-18 content
        """
        print(f"Searching for images with tags: {', '.join(tags)}")

        # Search URL
        search_url = "https://www.pixiv.net/ajax/search/artworks/" + \
            "%20".join(tags)
        params = {
            'word': " ".join(tags),
            'order': 'date_d',
            'mode': 'all',
            'p': 1,
            's_mode': mode,
            'type': 'all',
            'lang': 'ko',
            'rating': rating
        }

        downloaded_count = 0
        page = 1
        consecutive_errors = 0

        with tqdm(total=max_images, desc="Downloading images") as pbar:
            while downloaded_count < max_images:
                try:
                    # Update page number
                    params['p'] = page

                    # Get search results
                    response = self.session.get(search_url, params=params)
                    response.raise_for_status()
                    data = response.json()

                    if not data.get('body', {}).get('illustManga', {}).get('data'):
                        break

                    # Process each illustration
                    for illust in data['body']['illustManga']['data']:
                        if downloaded_count >= max_images:
                            break

                        # Skip if not single image
                        if illust.get('illustType') != 0:  # 0 = single image
                            continue

                        # Get image URL and metadata
                        image_urls, metadata_list = self.get_image_details(illust['id'])

                        if not image_urls or not metadata_list:
                            continue

                        for page_index, (image_url, metadata) in enumerate(zip(image_urls, metadata_list)):
                            if self.download_image(image_url, illust['id'], metadata, page_index):
                                downloaded_count += 1
                                pbar.update(1)
                                consecutive_errors = 0

                            if downloaded_count >= max_images:
                                break

                            time.sleep(2)
                    
                    page += 1
                    time.sleep(4)  # Wait between pages

                except Exception as e:
                    print(f"Error during search: {str(e)}")
                    consecutive_errors += 1

                    # If we get too many errors, rotate cookie
                    if consecutive_errors >= 1:
                        self.rotate_cookie()
                        consecutive_errors = 0

                    time.sleep(5)  # Wait before retrying
                    continue
                
        print(f"Downloaded {downloaded_count} images to {self.output_dir}")
        print(f"Metadata saved to {self.metadata_dir}")


def main():
    parser = argparse.ArgumentParser(description='Pixiv image crawler')
    parser.add_argument('--cookie-file', required=True,
                        help='File containing Pixiv PHPSESSID cookies (one per line)')
    parser.add_argument('--tags', required=True, nargs='+',
                        help='Tags to search for (space-separated)')
    parser.add_argument(
        '--output-dir', default='images', help='Output directory')
    parser.add_argument('--max-images', type=int, default=100000,
                        help='Maximum number of images to download')
    parser.add_argument('--mode', choices=['s_tag_full', 's_tag'], default='s_tag',
                        help='Search mode: s_tag_full (all tags must match) or s_tag (any tag can match)')
    parser.add_argument('--rating', choices=['all', 'safe', 'r18'], default='all',
                        help='Content rating: all, safe, or r18')
    args = parser.parse_args()

    crawler = PixivCrawler(args.cookie_file, args.output_dir)
    crawler.search_and_download(
        args.tags, args.max_images, args.mode, args.rating)


if __name__ == "__main__":
    main()
