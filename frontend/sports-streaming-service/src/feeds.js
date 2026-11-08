const DEFAULT_BASE = 'https://match-switcher-poc-videos.s3.eu-west-2.amazonaws.com';
const S3_BASE_URL = (process.env.REACT_APP_S3_BASE_URL || DEFAULT_BASE).replace(/\/$/, '');
const PREVIEW_BASE_URL = (process.env.REACT_APP_PREVIEW_BASE_URL || S3_BASE_URL).replace(/\/$/, '');
const TEST_VIDEO_KEY = process.env.REACT_APP_TEST_VIDEO_KEY;
const PREVIEW_KEY = process.env.REACT_APP_TEST_PREVIEW_KEY;

// Each match is match-<n>.mp4 at the bucket root. Its lightweight preview
// (used by the small tiles) sits next to it as match-<n>-preview-v1.mp4.
// REACT_APP_TEST_VIDEO_KEY / REACT_APP_TEST_PREVIEW_KEY force every feed to one video, for testing.
// The backend names feeds "cam-1" ... "cam-7", in the order of VIDEO_KEYS in backend/main.py.
const previewKeyFor = (key) => key.replace(/\.mp4$/i, '-preview-v1.mp4');

export const FEEDS = Array.from({ length: 7 }, (_, i) => {
  const mainKey = TEST_VIDEO_KEY || `match-${i + 1}.mp4`;
  return {
    id: i + 1,
    label: `Match ${i + 1}`,
    cameraId: `cam-${i + 1}`,
    mainKey,
    previewKey: PREVIEW_KEY || previewKeyFor(mainKey),
  };
});

const objectUrl = (base, key) => `${base}/${key.split('/').map(encodeURIComponent).join('/')}`;
export const getVideoUrl = (feed) => objectUrl(S3_BASE_URL, feed.mainKey || feed.key);
export const getPreviewUrl = (feed) => objectUrl(PREVIEW_BASE_URL, feed.previewKey);

// Maps a backend `target_feed` ("cam-3", "3" or 3) to a feed id, or null if unknown.
export function feedIdFromTarget(target) {
  const match = String(target ?? '').trim().match(/(\d+)$/);
  const id = match ? Number(match[1]) : NaN;
  return FEEDS.some((feed) => feed.id === id) ? id : null;
}
