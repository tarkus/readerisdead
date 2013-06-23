import argparse
import getpass
import itertools
import logging
import os.path
import urllib
import urllib2
import sys

import base.api
import base.log
import base.tag_helper
import base.worker

def main():
  base.log.init()

  parser = argparse.ArgumentParser(
      description='Comprehensive archive a Google Reader account')

  # Credentials
  parser.add_argument('--account', default='',
                      help='Google Account to save the archive for. Omit to '
                          'specify via standard input')
  parser.add_argument('--password', default='',
                      help='Password for the account. Omit to specify via '
                          'standard input')

  # Output options
  parser.add_argument('--output_directory', default='./',
                      help='Directory where to place archive data.')

  # Fetching options
  parser.add_argument('--stream_items_chunk_size', type=int, default=10000,
                      help='Number of items refs to request per stream items '
                           'API call (higher is more efficient)')
  parser.add_argument('--item_bodies_chunk_size', type=int, default=250,
                      help='Number of items refs per request for fetching their '
                           'bodies (higher is more efficient)')
  parser.add_argument('--parallelism', type=int, default=10,
                      help='Number of requests to make in parallel.')

  args = parser.parse_args()

  output_directory = base.paths.normalize(args.output_directory)
  base.paths.ensure_exists(output_directory)
  api_responses_directory = os.path.join(output_directory, '_raw_data')

  auth_token = _get_auth_token(args.account, args.password)

  if not auth_token:
    logging.error('Could not fetch authentication token.')
    sys.exit(1)

  api = base.api.Api(auth_token, cache_directory=api_responses_directory)

  user_info = api.fetch_user_info()
  logging.info(
    'Created API instance for %s (%s)', user_info.user_id, user_info.email)

  logging.info('Gathering streams to fetch')
  stream_ids = _get_stream_ids(api, user_info.user_id)
  logging.info('%d streams to fetch, gathering item refs:', len(stream_ids))

  item_refs_responses = base.worker.do_work(
      lambda: FeedItemRefsWorker(api, args.stream_items_chunk_size),
      stream_ids,
      args.parallelism)

  logging.info('Gathered item refs:')

  item_ids = set()
  item_refs_total = 0
  for stream_id, item_refs in itertools.izip(stream_ids, item_refs_responses):
    logging.info('  %d item refs from %s', len(item_refs), stream_id)
    item_ids.update([item_ref.item_id for item_ref in item_refs])
    item_refs_total += len(item_refs)
  item_ids = list(item_ids)
  logging.info('%d unique items refs (%d total), getting item bodies:',
      len(item_ids), item_refs_total)

def _get_auth_token(account, password):
  account = account or raw_input('Google Account username: ')
  password = password or getpass.getpass('Password: ')
  credentials_data = urllib.urlencode({
    'Email': account,
    'Passwd': password,
    'service': 'reader',
    'accountType': 'GOOGLE',
  })
  try:
    auth_response = urllib2.urlopen(
        'https://www.google.com/accounts/ClientLogin', credentials_data)
  except urllib2.HTTPError, e:
    logging.error(
        'Error response while fetching authentication token: %s %s',
        e.code, e.message)
    return None
  auth_token = None
  for line in auth_response.readlines():
    key, value = line.strip().split('=', 1)
    if key == 'Auth':
      auth_token = value
      break
  auth_response.close()
  assert auth_token
  return auth_token

def _get_stream_ids(api, user_id):
  tag_helper = base.tag_helper.TagHelper(user_id)
  stream_ids = set(tag_helper.system_tags())
  stream_ids.update([tag.stream_id for tag in api.fetch_tags()])
  stream_ids.update([sub.stream_id for sub in api.fetch_subscriptions()])
  stream_ids.update([
    f.stream_id for f in api.fetch_friends() if f.stream_id and f.is_following])
  stream_ids = list(stream_ids)
  # Start the fetch with user streams, since those tend to have more items and
  # are thus the long pole.
  stream_ids.sort(reverse=True)
  return stream_ids

class FeedItemRefsWorker(base.worker.Worker):
  def __init__(self, api, chunk_size):
    self._api = api
    self._chunk_size = chunk_size

  def work(self, stream_id):
    result = []
    continuation_token = None
    while True:
      item_refs, continuation_token = self._api.fetch_item_refs(
          stream_id,
          count=self._chunk_size,
          continuation_token=continuation_token)
      logging.info('  Loaded %d item refs from %s', len(item_refs), stream_id)
      result.extend(item_refs)
      if not continuation_token:
        break
    return result

if __name__ == '__main__':
    main()

