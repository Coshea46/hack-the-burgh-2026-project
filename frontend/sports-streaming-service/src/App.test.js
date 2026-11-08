import { render, screen, fireEvent, within } from '@testing-library/react';
import App from './App';
import MainPlayer, { boundedTime } from './components/MainPlayer';
import { FEEDS, getVideoUrl, getPreviewUrl } from './feeds';

beforeEach(() => localStorage.clear());

function ready(video) {
  Object.defineProperty(video, 'readyState', { configurable: true, value: 2 });
  Object.defineProperty(video, 'duration', { configurable: true, value: 418.69 });
  fireEvent.loadedMetadata(video);
  fireEvent.canPlay(video);
}

test('opens one S3 main player and six visible lightweight previews', () => {
  render(<App />);
  const main = screen.getByLabelText('Match 1 video');
  expect(main).toHaveAttribute('src', getVideoUrl(FEEDS[0]));
  expect(main).toHaveAttribute('controls');
  const strip = screen.getByRole('region', { name: 'Other matches' });
  expect(within(strip).getAllByRole('button')).toHaveLength(6);
  expect(strip.querySelectorAll('video')).toHaveLength(7);
  strip.querySelectorAll('video').forEach((video, i) => {
    expect(video).toHaveAttribute('src', getPreviewUrl(FEEDS[i]));
    expect(video.getAttribute('src')).not.toBe(getVideoUrl(FEEDS[i]));
  });
  expect(getVideoUrl(FEEDS[0])).toMatch(/\/match-1\.mp4$/);
  expect(getPreviewUrl(FEEDS[6])).toMatch(/\/match-7-preview-v1\.mp4$/);
});

test('switching preserves every video DOM node and the shared-source main timestamp', () => {
  const { container } = render(<App />);
  const main = screen.getByLabelText('Match 1 video');
  ready(main);
  main.currentTime = 125;
  fireEvent.timeUpdate(main);
  const videos = Array.from(container.querySelectorAll('video'));
  fireEvent.click(screen.getByRole('button', { name: 'Match 3' }));
  expect(screen.getByLabelText('Match 3 video')).toBe(main);
  expect(main.currentTime).toBe(125);
  Array.from(container.querySelectorAll('video')).forEach((video, index) => expect(video).toBe(videos[index]));
  expect(screen.getByRole('button', { name: 'Match 1' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Match 3' })).toHaveFocus();
});

test('a genuinely different main source restores timeline, pause, rate and volume', () => {
  const clock = { current: { time: 0, playing: true, rate: 1, muted: false, volume: 1 } };
  const { rerender } = render(<MainPlayer feed={{ id: 1, label: 'A', mainKey: 'a.mp4' }} clock={clock} />);
  const video = screen.getByLabelText('A video');
  ready(video);
  video.currentTime = 82;
  video.playbackRate = 1.5;
  video.volume = 0.4;
  video.muted = true;
  fireEvent.timeUpdate(video);
  fireEvent.pause(video);
  const play = jest.spyOn(video, 'play');
  play.mockClear();
  rerender(<MainPlayer feed={{ id: 2, label: 'B', mainKey: 'b.mp4' }} clock={clock} />);
  expect(screen.getByLabelText('B video')).toBe(video);
  video.currentTime = 0; // Simulate the browser resetting time for a new resource.
  ready(video);
  expect(video.currentTime).toBe(82);
  expect(video.playbackRate).toBe(1.5);
  expect(video.volume).toBe(0.4);
  expect(video.muted).toBe(true);
  expect(play).not.toHaveBeenCalled();
  play.mockRestore();
});

test('Space and scoped number shortcuts continue to select matches', () => {
  render(<App />);
  fireEvent.keyDown(window, { key: '4' });
  expect(screen.getByLabelText('Match 1 video')).toBeInTheDocument();
  fireEvent.keyDown(screen.getByRole('button', { name: 'Match 2' }), { key: ' ' });
  expect(screen.getByLabelText('Match 2 video')).toBeInTheDocument();
  fireEvent.keyDown(screen.getByRole('heading', { name: 'Match 2' }), { key: '4' });
  expect(screen.getByLabelText('Match 4 video')).toBeInTheDocument();
  fireEvent.keyDown(screen.getByRole('heading', { name: 'Match 4' }), { key: 'Escape' });
  expect(screen.getByRole('button', { name: 'Match 1' })).toHaveFocus();
});

test('pause previews never pauses the main element, and selection keeps previews paused', () => {
  const pause = jest.spyOn(window.HTMLMediaElement.prototype, 'pause');
  render(<App />);
  const main = screen.getByLabelText('Match 1 video');
  pause.mockClear();
  fireEvent.click(screen.getByRole('button', { name: 'Pause previews' }));
  expect(pause).toHaveBeenCalledTimes(7);
  expect(pause.mock.instances).not.toContain(main);
  fireEvent.click(screen.getByRole('button', { name: 'Match 3' }));
  expect(screen.getByRole('button', { name: 'Resume previews' })).toHaveAttribute('aria-pressed', 'true');
  expect(pause.mock.instances).not.toContain(main);
  pause.mockRestore();
});

test('a returning preview seeks to the main timeline without being recreated', () => {
  const { container } = render(<App />);
  const main = screen.getByLabelText('Match 1 video');
  const preview = container.querySelector('[data-feed-id="1"] video');
  ready(main);
  ready(preview);
  main.currentTime = 100;
  fireEvent.timeUpdate(main);
  fireEvent.click(screen.getByRole('button', { name: 'Match 3' }));
  expect(container.querySelector('[data-feed-id="1"] video')).toBe(preview);
  expect(preview.currentTime).toBe(100);
});

test('themes persist without replacing media elements', () => {
  const { unmount } = render(<App />);
  const main = screen.getByLabelText('Match 1 video');
  fireEvent.click(screen.getByRole('button', { name: 'Switch to light mode' }));
  expect(screen.getByLabelText('Match 1 video')).toBe(main);
  expect(localStorage.getItem('match-switcher-theme')).toBe('light');
  unmount();
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Switch to dark mode' }));
  expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
});

test('main failures expose retry; a missing preview falls back to the full video once', () => {
  const { container } = render(<App />);
  fireEvent.error(screen.getByLabelText('Match 1 video'));
  expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  const preview = container.querySelector('[data-feed-id="2"] video');
  expect(preview).toHaveAttribute('src', getPreviewUrl(FEEDS[1]));
  fireEvent.error(preview);
  expect(preview).toHaveAttribute('src', getVideoUrl(FEEDS[1]));
  expect(screen.queryByText('Preview unavailable')).not.toBeInTheDocument();
  fireEvent.error(preview);
  expect(screen.getByText('Preview unavailable')).toBeInTheDocument();
});

test('seek targets remain within the destination duration', () => {
  expect(boundedTime(500, 100)).toBe(99.9);
  expect(boundedTime(-10, 100)).toBe(0);
  expect(boundedTime(25, NaN)).toBe(25);
});

describe('backend WebSocket', () => {
  const { act } = require('@testing-library/react');
  const { feedIdFromTarget } = require('./feeds');
  const socket = () => global.FakeWebSocket.instances.at(-1);
  const send = (message) => act(() => { socket().open(); socket().receive(message); });

  test('maps backend feed names to matches', () => {
    expect(feedIdFromTarget('cam-3')).toBe(3);
    expect(feedIdFromTarget('3')).toBe(3);
    expect(feedIdFromTarget(7)).toBe(7);
    expect(feedIdFromTarget('cam-9')).toBeNull();
    expect(feedIdFromTarget(undefined)).toBeNull();
  });

  test('connects to the backend and shows the connection state', () => {
    render(<App />);
    expect(socket().url).toBe('ws://localhost:8000');
    expect(screen.getByText('Connecting')).toBeInTheDocument();
    act(() => socket().open());
    expect(screen.getByText('Live')).toBeInTheDocument();
  });

  test('a switch message changes the main match without stealing focus', () => {
    render(<App />);
    const toggle = screen.getByRole('button', { name: 'Auto' });
    toggle.focus();
    send({ type: 'switch', target_feed: 'cam-3', from_timestamp: '0', to_timestamp: '5', window_id: 1 });
    expect(screen.getByLabelText('Match 3 video')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Match 3' })).not.toHaveFocus();
    expect(toggle).toHaveFocus();
    expect(screen.getByText('Switched to Match 3')).toBeInTheDocument();
  });

  test('unknown feeds and malformed messages are ignored', () => {
    render(<App />);
    send({ type: 'switch', target_feed: 'cam-42' });
    act(() => socket().receive('not json'));
    expect(screen.getByLabelText('Match 1 video')).toBeInTheDocument();
  });

  test('a manual pick holds off automatic switches for 30 seconds', () => {
    jest.useFakeTimers();
    try {
      render(<App />);
      fireEvent.click(screen.getByRole('button', { name: 'Match 2' }));
      expect(screen.getByRole('button', { name: 'Auto paused' })).toBeInTheDocument();
      send({ type: 'switch', target_feed: 'cam-4' });
      expect(screen.getByLabelText('Match 2 video')).toBeInTheDocument();
      act(() => { jest.advanceTimersByTime(30001); });
      expect(screen.getByRole('button', { name: 'Auto' })).toBeInTheDocument();
      send({ type: 'switch', target_feed: 'cam-4' });
      expect(screen.getByLabelText('Match 4 video')).toBeInTheDocument();
    } finally {
      jest.useRealTimers();
    }
  });

  test('turning Auto off ignores the backend', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Auto' }));
    expect(screen.getByRole('button', { name: 'Auto off' })).toHaveAttribute('aria-pressed', 'false');
    send({ type: 'switch', target_feed: 'cam-5' });
    expect(screen.getByLabelText('Match 1 video')).toBeInTheDocument();
  });

  test('sync seeks the main player to the live timestamp once', () => {
    render(<App />);
    const main = screen.getByLabelText('Match 1 video');
    ready(main);
    send({ type: 'sync', current_live_timestamp: 125 });
    expect(main.currentTime).toBe(125);
    main.currentTime = 200;
    act(() => { socket().drop(); });
    send({ type: 'sync', current_live_timestamp: 0 });
    expect(main.currentTime).toBe(200);
  });

  test('reconnects with backoff after the backend drops', () => {
    jest.useFakeTimers();
    try {
      render(<App />);
      act(() => socket().open());
      act(() => socket().drop());
      expect(screen.getByText('Offline')).toBeInTheDocument();
      const before = global.FakeWebSocket.instances.length;
      act(() => { jest.advanceTimersByTime(1000); });
      expect(global.FakeWebSocket.instances.length).toBe(before + 1);
    } finally {
      jest.useRealTimers();
    }
  });
});
