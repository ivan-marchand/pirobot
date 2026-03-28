import React from 'react';
import { render, screen } from '@testing-library/react';
import VideoStreamControl from './VideoStreamControl';

// suppress WebSocket noise in tests
global.WebSocket = class {
  constructor() { this.onopen = null; this.onmessage = null; this.onclose = null; this.onerror = null; }
  send() {}
  close() {}
};

test('renders img with CSS fill styles (no maxHeight/maxWidth)', () => {
  render(<VideoStreamControl updateFps={() => {}} />);
  const img = screen.getByAltText('Camera Feed');
  expect(img).toHaveStyle({ width: '100%', height: '100%', objectFit: 'contain' });
});

test('renders without max_height or max_width props', () => {
  // should not throw when these props are absent
  expect(() => render(<VideoStreamControl updateFps={() => {}} />)).not.toThrow();
});
