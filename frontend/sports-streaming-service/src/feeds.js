const DEFAULT_BASE = 'https://match-switcher-poc-videos.s3.eu-west-2.amazonaws.com';
const DEFAULT_KEY = 'matches/230024607-Video_presentation.mp4';
const S3_BASE_URL = (process.env.REACT_APP_S3_BASE_URL || DEFAULT_BASE).replace(/\/$/, '');
const PREVIEW_BASE_URL = (process.env.REACT_APP_PREVIEW_BASE_URL || S3_BASE_URL).replace(/\/$/, '');
const TEST_VIDEO_KEY = process.env.REACT_APP_TEST_VIDEO_KEY || DEFAULT_KEY;
const PREVIEW_KEY = process.env.REACT_APP_TEST_PREVIEW_KEY;

// Previews live next to their main video in S3 (matches/<name>-preview-v1.mp4), never bundled with the app.
// Give each real match its own mainKey and matching previewKey.
// The backend names feeds "cam-1" ... "cam-7", in the order of VIDEO_KEYS in backend/main.py.
export const FEEDS = Array.from({ length: 7 }, (_, i) => ({
  id: i + 1,
  label: `Match ${i + 1}`,
  cameraId: `cam-${i + 1}`,
  mainKey: TEST_VIDEO_KEY,
  previewKey: PREVIEW_KEY || TEST_VIDEO_KEY.replace(/\.mp4$/i, '-preview-v1.mp4'),
}));

const objectUrl = (base, key) => `${base}/${key.split('/').map(encodeURIComponent).join('/')}`;
export const getVideoUrl = (feed) => objectUrl(S3_BASE_URL, feed.mainKey || feed.key);
export const getPreviewUrl = (feed) => objectUrl(PREVIEW_BASE_URL, feed.previewKey);

// Maps a backend `target_feed` ("cam-3", "3" or 3) to a feed id, or null if unknown.
export function feedIdFromTarget(target) {
  const match = String(target ?? '').trim().match(/(\d+)$/);
  const id = match ? Number(match[1]) : NaN;
  return FEEDS.some((feed) => feed.id === id) ? id : null;
}
