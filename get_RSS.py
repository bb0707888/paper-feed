import feedparser
import re
import os
import datetime
import time
from rfeed import Item, Feed, Guid
from email.utils import parsedate_to_datetime

# --- 配置区域 ---
OUTPUT_FILE = "filtered_feed.xml"
MAX_ITEMS = 1000
# ----------------

def load_config(filename, env_var_name=None):
    """(保持你之前的 load_config 代码不变)"""
    # ... 请保留你之前为了隐私修改过的 load_config 函数 ...
    # 这里为了篇幅省略，请直接复用你现在的 load_config
    if env_var_name and os.environ.get(env_var_name):
        print(f"Loading config from environment variable: {env_var_name}")
        content = os.environ[env_var_name]
        if '\n' in content:
            return [line.strip() for line in content.split('\n') if line.strip()]
        else:
            return [line.strip() for line in content.split(';') if line.strip()]
            
    if os.path.exists(filename):
        print(f"Loading config from local file: {filename}")
        with open(filename, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
    return []

# --- 新增：XML 非法字符清洗函数 ---
def remove_illegal_xml_chars(text):
    """
    移除 XML 1.0 不支持的 ASCII 控制字符 (Char value 0-8, 11-12, 14-31)
    """
    if not text:
        return ""
    # 正则表达式：匹配 ASCII 0-8, 11, 12, 14-31 这些控制字符
    # \x09是tab, \x0a是换行, \x0d是回车，这些是合法的，所以不删
    illegal_chars = r'[\x00-\x08\x0b\x0c\x0e-\x1f]'
    return re.sub(illegal_chars, '', text)

def convert_struct_time_to_datetime(struct_time):
    if not struct_time:
        return datetime.datetime.now()
    return datetime.datetime.fromtimestamp(time.mktime(struct_time))

def parse_rss(rss_url, retries=3):
    # (保持不变)
    print(f"Fetching: {rss_url}...")
    for attempt in range(retries):
        try:
            feed = feedparser.parse(rss_url)
            entries = []
            journal_title = feed.feed.get('title', 'Unknown Journal')
            
            for entry in feed.entries:
                pub_struct = entry.get('published_parsed', entry.get('updated_parsed'))
                pub_date = convert_struct_time_to_datetime(pub_struct)
                
                entries.append({
                    'title': entry.get('title', ''),
                    'link': entry.get('link', ''),
                    'pub_date': pub_date,
                    'summary': entry.get('summary', entry.get('description', '')),
                    'journal': journal_title,
                    'id': entry.get('id', entry.get('link', ''))
                })
            return entries
        except Exception as e:
            print(f"Error parsing {rss_url}: {e}")
            time.sleep(2)
    return []

def get_existing_items():
    # (保持不变，但增加容错：如果 XML 坏了，就返回空列表重新抓)
    if not os.path.exists(OUTPUT_FILE):
        return []
    
    print(f"Loading existing items from {OUTPUT_FILE}...")
    try:
        feed = feedparser.parse(OUTPUT_FILE)
        # 如果解析出错（比如现在的 invalid char），feedparser 可能会拿到空或者 bozo 标志
        if hasattr(feed, 'bozo') and feed.bozo == 1:
             print("Warning: Existing XML file might be corrupted. Ignoring old items.")
             # 这里可以选择 return [] 直接丢弃坏掉的旧数据，重新开始
             # return [] 
             # 或者尝试读取能读的部分（取决于损坏位置）
        
        entries = []
        for entry in feed.entries:
            pub_struct = entry.get('published_parsed')
            pub_date = convert_struct_time_to_datetime(pub_struct)
            
            entries.append({
                'title': entry.get('title', ''),
                'link': entry.get('link', ''),
                'pub_date': pub_date,
                'summary': entry.get('summary', ''),
                'journal': entry.get('author', ''),
                'id': entry.get('id', entry.get('link', '')),
                'is_old': True
            })
        return entries
    except Exception as e:
        print(f"Error reading existing file: {e}")
        return [] # 如果旧文件读不了，就当做第一次运行

def match_entry(entry, queries):
    # (保持不变)
    text_to_search = (entry['title'] + " " + entry['summary']).lower()
    for query in queries:
        keywords = [k.strip().lower() for k in query.split('AND')]
        match = True
        for keyword in keywords:
            if keyword not in text_to_search:
                match = False
                break
        if match:
            return True
    return False

def generate_rss_xml(items):
    """生成 RSS 2.0 XML 文件 (已加入非法字符清洗)"""
    rss_items = []
    
    items.sort(key=lambda x: x['pub_date'], reverse=True)
    items = items[:MAX_ITEMS]
    
    for item in items:
        title = item['title']
        if not item.get('is_old', False):
            title = f"[{item['journal']}] {item['title']}"
            
        # --- 关键修改：清洗数据 ---
        clean_title = remove_illegal_xml_chars(title)
        clean_summary = remove_illegal_xml_chars(item['summary'])
        clean_journal = remove_illegal_xml_chars(item['journal'])
        # -----------------------

        rss_item = Item(
            title = clean_title,
            link = item['link'],
            description = clean_summary,
            author = clean_journal,
            guid = Guid(item['id']),
            pubDate = item['pub_date']
        )
        rss_items.append(rss_item)

    feed = Feed(
        title = "My Customized Papers",
        link = "https://github.com/your_username/your_repo",
        description = "Aggregated research papers",
        language = "en-US",
        lastBuildDate = datetime.datetime.now(),
        items = rss_items
    )

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(feed.rss())
    print(f"Successfully generated {OUTPUT_FILE} with {len(rss_items)} items.")

def main():
    # 请确保这里的调用参数与你目前的 secrets 配置一致
    rss_urls = load_config('journals.dat', 'RSS_JOURNALS')
    queries = load_config('keywords.dat', 'RSS_KEYWORDS')
    
    if not rss_urls or not queries:
        print("Error: Configuration files are empty or missing.")
        return

    existing_entries = get_existing_items()
    seen_ids = set(entry['id'] for entry in existing_entries)
    
    all_entries = existing_entries.copy()
    new_count = 0

    print("Starting RSS fetch from remote...")
    for url in rss_urls:
        fetched_entries = parse_rss(url)
        for entry in fetched_entries:
            if entry['id'] in seen_ids:
                continue
            
            if match_entry(entry, queries):
                all_entries.append(entry)
                seen_ids.add(entry['id'])
                new_count += 1
                print(f"Match found: {entry['title'][:50]}...")

    print(f"Added {new_count} new entries.")
    generate_rss_xml(all_entries)

if __name__ == '__main__':
    main()