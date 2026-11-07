const S3_BASE_URL = (
  process.env.REACT_APP_S3_BASE_URL ||
  'https://match-switcher-poc-videos.s3.eu-west-2.amazonaws.com'
).replace(/\/$/, '');

// Only one test video exists for now, so every feed reuses it.
// Replace each `key` with its own S3 object key once more videos are uploaded.
const TEST_VIDEO_KEY = process.env.REACT_APP_TEST_VIDEO_KEY || 'matches/230024607-Video_presentation.mp4';

export const FEEDS = Array.from({ length: 7 }, (_, i) => ({
  id: i + 1,
  label: `Match ${i + 1}`,
  key: TEST_VIDEO_KEY,
}));

export const getVideoUrl = (feed) =>
  `${S3_BASE_URL}/${feed.key.split('/').map(encodeURIComponent).join('/')}`;
