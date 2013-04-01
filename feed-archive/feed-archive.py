import argparse
import datetime
import logging
import sys
import urllib
import urllib2
import xml.etree.cElementTree as ET

import log

_BASE_PARAMETERS = {
  'mediaRss': 'true',
  'client': 'reader-feed-archive'
}

_ATOM_NS = 'http://www.w3.org/2005/Atom'
_READER_NS = 'http://www.google.com/schemas/reader/atom/'

ET.register_namespace('gr', _READER_NS)
ET.register_namespace('atom', _ATOM_NS)
ET.register_namespace('idx', 'urn:atom-extension:indexing')
ET.register_namespace('media', 'http://search.yahoo.com/mrss/')

def main():
  log.init()
  parser = argparse.ArgumentParser(
      description='Fetch archived feed data from Google Reader')
  parser.add_argument('feed_urls', metavar='feed_url', nargs='+',
                      help='Feed URL to fetch archived data for')
  parser.add_argument('--chunk_size', type=int, default=1000,
                      help='Number of items to request per Google Reader API '
                           'call (higher is more efficient)')
  parser.add_argument('--max_items', type=int, default=0,
                      help='Maxmium number of items to fetch per feed (0 for '
                           'no limit)')
  parser.add_argument('--oldest_item_timestamp_sec', type=int, default=0,
                      help='Timestamp (in seconds since the epoch) of the '
                           'oldest item that should be returned (0 for no '
                           'timestamp restriction)')
  parser.add_argument('--newest_item_timestamp_sec', type=int, default=0,
                      help='Timestamp (in seconds since the epoch) of the '
                           'newest item that should be returned (0 for no '
                           'timestamp restriction)')
  args = parser.parse_args()
  _BASE_PARAMETERS['n'] = args.chunk_size
  if args.oldest_item_timestamp_sec:
    _BASE_PARAMETERS['ot'] = args.oldest_item_timestamp_sec
  if args.newest_item_timestamp_sec:
    _BASE_PARAMETERS['nt'] = args.newest_item_timestamp_sec
  for feed_url in args.feed_urls:
    fetch_feed(feed_url, args.max_items)

# params
# - retry attempts
# - OPML file (local or remote) to use for feed URLs

def fetch_feed(feed_url, max_items):
  continuation_token = None
  combined_feed = None
  total_entries = 0
  while True:
    parameters = _BASE_PARAMETERS.copy()
    if continuation_token:
      parameters['c'] = continuation_token
    reader_url = (
      'http://www.google.com/reader/public/atom/hifi/feed/%s?%s' %
      (urllib.quote(feed_url), urllib.urlencode(parameters)))
    logging.debug("Fetching %s", reader_url)
    request = urllib2.Request(reader_url)
    response = urllib2.urlopen(request)
    response_tree = ET.parse(response)
    response_root = response_tree.getroot()
    entries = response_root.findall('{%s}entry' % _ATOM_NS)
    oldest_message = ""
    if entries:
      last_crawl_timestamp_msec = \
          entries[-1].attrib['{%s}crawl-timestamp-msec' % _READER_NS]
      last_crawl_timestamp = datetime.datetime.utcfromtimestamp(
          float(last_crawl_timestamp_msec)/1000)
      oldest_message = " (oldest is from %s)" % last_crawl_timestamp
    logging.info("Loaded %d entries%s", len(entries), oldest_message)
    if combined_feed:
      combined_feed.extend(entries)
    else:
      combined_feed = response_root
    continuation_element = response_root.find(
        '{%s}continuation' % _READER_NS)
    if continuation_element is not None:
      # TODO: explain
      response_root.remove(continuation_element)
      continuation_token = continuation_element.text
    else:
      break
    total_entries += len(entries)
    if max_items and total_entries >= max_items:
      break
  combined_feed_tree = ET.ElementTree(combined_feed)
  combined_feed_tree.write(
      sys.stdout,
      xml_declaration=True,
      encoding='utf-8')

if __name__ == "__main__":
    main()
