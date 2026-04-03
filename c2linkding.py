"""
将书签数据从 YAML 文件更新到 linkding 实例（https://linkding.link）的脚本，使用其 REST API。

此脚本读取包含书签数据的 YAML 文件，检查每个书签的 URL 是否已存在于 linkding 服务器上，
并为不存在的 URL 创建新书签。书签会使用 YAML 文件中的分类（taxonomy）和子分类（term）作为标签。

依赖项：
- Python 3.6 或以上版本
- requests 库 (`pip install requests`)
- pyyaml 库 (`pip install pyyaml`)
- 有效的 linkding API 令牌，需通过 LINKDING_API_TOKEN 环境变量设置

使用方法：
    设置 LINKDING_API_TOKEN 环境变量并运行脚本，传入 YAML 文件路径：
    ```bash
    LINKDING_API_TOKEN=your_token python update_bookmarks.py path/to/bookmarks.yaml
    ```

YAML 文件结构示例：
```yaml
- taxonomy: 分类1
  list:
    - term: 子分类1
      links:
        - title: 书签标题
          url: https://example.com
          description: 书签描述
```

脚本会跳过缺少 URL 的书签以及已存在的书签，以避免重复。
"""

import yaml
import requests
import sys
import os

# Configuration
API_BASE_URL = "https://link.asfd.cn/api/bookmarks/"
LINKDING_API_TOKEN = os.getenv("LINKDING_API_TOKEN")  # Retrieve API token from environment variable

if os.getenv("KEY"):
    LINKDING_API_TOKEN = os.getenv("KEY")
if not LINKDING_API_TOKEN:
    print("Error: LINKDING_API_TOKEN environment variable not set")
    sys.exit(1)
HEADERS = {"Authorization": f"Token {LINKDING_API_TOKEN}"}

def check_bookmark_exists(url):
    """Check if a bookmark with the given URL already exists."""
    check_url = f"{API_BASE_URL}check/?url={requests.utils.quote(url)}"
    try:
        response = requests.get(check_url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        return data.get("bookmark") is not None
    except requests.RequestException as e:
        print(f"Error checking URL {url}: {e}")
        return False

def create_bookmark(title, url, description, tags):
    """Create a new bookmark with the given data."""
    payload = {
        "title": title,
        "url": url,
        "description": description,
        "tag_names": tags,
        "is_archived": False,
        "unread": False,
        "shared": True
    }
    try:
        response = requests.post(API_BASE_URL, json=payload, headers=HEADERS)
        response.raise_for_status()
        print(f"Successfully created bookmark: {title} ({url})")
    except requests.RequestException as e:
        print(f"Error creating bookmark {title} ({url}): {e}")

def main(yaml_file_path):
    """Parse YAML file and update bookmarks."""
    try:
        with open(yaml_file_path, 'r', encoding='utf-8') as file:
            data = yaml.safe_load(file)
    except Exception as e:
        print(f"Error reading YAML file: {e}")
        sys.exit(1)

    for taxonomy_entry in data:
        taxonomy = taxonomy_entry.get('taxonomy', '')
        for list_item in taxonomy_entry.get('list', []):
            term = list_item.get('term', '')
            # tags = [taxonomy, term]  # Use taxonomy and term as tags
            tags = [term]  # Use taxonomy and term as tags
            for link in list_item.get('links', []):
                title = link.get('title', '')
                url = link.get('url', '')
                description = link.get('description', '')

                if not url:
                    print(f"Skipping link with missing URL in {title}")
                    continue

                # Check if the URL already exists
                if check_bookmark_exists(url):
                    print(f"Bookmark already exists, skipping: {title} ({url})")
                    continue

                # Create new bookmark
                create_bookmark(title, url, description, tags)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python update_bookmarks.py <yaml_file_path>")
        sys.exit(1)
    main(sys.argv[1])
