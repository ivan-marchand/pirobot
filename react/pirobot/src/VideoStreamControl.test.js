import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import VideoStreamControl from './VideoStreamControl';

const baseProps = {
  updateFps: () => {},
  sendWebRTCMessage: () => {},
  talking: false,
  listening: false,
};

test('renders a video element', () => {
  render(<VideoStreamControl {...baseProps} />);
  expect(document.querySelector('video')).toBeInTheDocument();
});

test('renders video element with correct inline styles', () => {
  render(<VideoStreamControl {...baseProps} />);
  const video = document.querySelector('video');
  expect(video).toHaveStyle({ width: '100%', height: '100%', objectFit: 'contain' });
});

test('renders without throwing when sendWebRTCMessage and updateFps are provided', () => {
  expect(() => render(<VideoStreamControl {...baseProps} />)).not.toThrow();
});

test('renders PiP video element when talking=true', () => {
  render(<VideoStreamControl {...baseProps} talking={true} />);
  const videos = document.querySelectorAll('video');
  expect(videos.length).toBe(2);
});

test('does not render PiP video element when talking=false', () => {
  render(<VideoStreamControl {...baseProps} talking={false} />);
  const videos = document.querySelectorAll('video');
  expect(videos.length).toBe(1);
});

test('renders hidden audio element', () => {
  render(<VideoStreamControl {...baseProps} />);
  const audio = document.querySelector('audio');
  expect(audio).toBeInTheDocument();
  expect(audio.style.display).toBe('none');
});

test('renders mute and camera buttons when talking=true', () => {
  render(<VideoStreamControl {...baseProps} talking={true} />);
  expect(screen.getByRole('button', { name: /mute microphone/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /turn off camera/i })).toBeInTheDocument();
});

test('clicking mute button toggles aria-label', () => {
  render(<VideoStreamControl {...baseProps} talking={true} />);
  const muteBtn = screen.getByRole('button', { name: /mute microphone/i });
  fireEvent.click(muteBtn);
  expect(screen.getByRole('button', { name: /unmute microphone/i })).toBeInTheDocument();
});

test('clicking mute button twice returns to unmuted state', () => {
  render(<VideoStreamControl {...baseProps} talking={true} />);
  const muteBtn = screen.getByRole('button', { name: /mute microphone/i });
  fireEvent.click(muteBtn);
  fireEvent.click(screen.getByRole('button', { name: /unmute microphone/i }));
  expect(screen.getByRole('button', { name: /mute microphone/i })).toBeInTheDocument();
});

test('clicking camera button shows camera-off placeholder', () => {
  render(<VideoStreamControl {...baseProps} talking={true} />);
  const camBtn = screen.getByRole('button', { name: /turn off camera/i });
  fireEvent.click(camBtn);
  expect(screen.getByTestId('camera-off-placeholder')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /turn on camera/i })).toBeInTheDocument();
});

test('PiP video element stays in DOM when camera is off', () => {
  render(<VideoStreamControl {...baseProps} talking={true} />);
  fireEvent.click(screen.getByRole('button', { name: /turn off camera/i }));
  const videos = document.querySelectorAll('video');
  const pip = videos[1];
  expect(pip).toBeInTheDocument();
  expect(pip.style.display).toBe('none');
});

test('renders without error when listening=true and talking=false', () => {
  expect(() => render(<VideoStreamControl {...baseProps} listening={true} />)).not.toThrow();
});

test('listening change while talking=true does not reset muted state', () => {
  const { rerender } = render(
    <VideoStreamControl {...baseProps} talking={true} listening={false} />
  );
  // Mute mic so we can detect if state was reset by a restart
  fireEvent.click(screen.getByRole('button', { name: /mute microphone/i }));
  expect(screen.getByRole('button', { name: /unmute microphone/i })).toBeInTheDocument();

  // Change listening while still talking — should NOT restart, muted stays true
  rerender(<VideoStreamControl {...baseProps} talking={true} listening={true} />);
  expect(screen.getByRole('button', { name: /unmute microphone/i })).toBeInTheDocument();
});

test('listening change while talking=false sends a new WebRTC offer with listening=true', async () => {
  const makeMockPc = () => {
    const pc = {
      addTransceiver: jest.fn().mockReturnValue({}),
      addTrack: jest.fn(),
      createOffer: jest.fn().mockResolvedValue({ sdp: 'fake-sdp', type: 'offer' }),
      setLocalDescription: jest.fn().mockImplementation(function(desc) {
        pc.localDescription = desc;
        return Promise.resolve();
      }),
      close: jest.fn(),
      onicecandidate: null,
      ontrack: null,
      localDescription: null,
    };
    return pc;
  };

  const savedRTCPeerConnection = global.RTCPeerConnection;
  global.RTCPeerConnection = jest.fn().mockImplementation(makeMockPc);

  const sendWebRTCMessage = jest.fn();

  await act(async () => {
    const { rerender } = render(
      <VideoStreamControl {...baseProps} sendWebRTCMessage={sendWebRTCMessage} talking={false} listening={false} />
    );
    await new Promise(resolve => setTimeout(resolve, 0));

    await act(async () => {
      rerender(<VideoStreamControl {...baseProps} sendWebRTCMessage={sendWebRTCMessage} talking={false} listening={true} />);
      await new Promise(resolve => setTimeout(resolve, 0));
    });
  });

  const offerCalls = sendWebRTCMessage.mock.calls.filter(([msg]) => msg.action === 'offer');
  expect(offerCalls.length).toBe(1); // from componentDidUpdate (mount with both false skips offer in jsdom timing)
  const lastOffer = offerCalls[offerCalls.length - 1][0];
  expect(lastOffer.listening).toBe(true);
  expect(lastOffer.talking).toBe(false);

  global.RTCPeerConnection = savedRTCPeerConnection;
});

test('talking change while listening=true includes listening=true in the offer', async () => {
  const mockPc = {
    addTransceiver: jest.fn().mockReturnValue({}),
    addTrack: jest.fn(),
    createOffer: jest.fn().mockResolvedValue({ sdp: 'fake-sdp', type: 'offer' }),
    setLocalDescription: jest.fn().mockImplementation(function(desc) {
      this.localDescription = desc;
      return Promise.resolve();
    }),
    close: jest.fn(),
    onicecandidate: null,
    ontrack: null,
  };
  global.RTCPeerConnection = jest.fn().mockReturnValue(mockPc);

  const sendWebRTCMessage = jest.fn();
  const { rerender } = render(
    <VideoStreamControl {...baseProps} sendWebRTCMessage={sendWebRTCMessage} talking={false} listening={true} />
  );

  await act(async () => {
    rerender(<VideoStreamControl {...baseProps} sendWebRTCMessage={sendWebRTCMessage} talking={true} listening={true} />);
    await new Promise(resolve => setTimeout(resolve, 0));
  });

  const offerCalls = sendWebRTCMessage.mock.calls.filter(([msg]) => msg.action === 'offer');
  const lastOffer = offerCalls[offerCalls.length - 1][0];
  expect(lastOffer.talking).toBe(true);
  expect(lastOffer.listening).toBe(true);

  delete global.RTCPeerConnection;
});
