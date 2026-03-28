# Responsive Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the PiRobot control UI render correctly on portrait mobile, landscape/tablet, and desktop by replacing JS pixel math with CSS breakpoints and MUI responsive utilities.

**Architecture:** Replace `window.innerWidth/Height` state and the resize listener with CSS-only sizing. Extract a `ResponsiveJoystick` functional wrapper (the only place hooks are needed). On mobile the outer container becomes `position:fixed;inset:0` with controls floating as overlays; on desktop the existing 3-column layout is preserved unchanged. The toolbar gains a primary/overflow split on small screens.

**Tech Stack:** React 18, MUI v5 (`@mui/material`, `@mui/icons-material`), react-joystick-component, @testing-library/react + Jest (via react-scripts)

---

## File Map

| File | Change |
|------|--------|
| `react/pirobot/src/ResponsiveJoystick.js` | **Create** — functional wrapper that uses `useMediaQuery` to pick joystick pixel size |
| `react/pirobot/src/ResponsiveJoystick.test.js` | **Create** — tests for breakpoint-dependent sizing |
| `react/pirobot/src/VideoStreamControl.js` | **Modify** — remove `max_height`/`max_width` props; `<img>` fills its container via CSS |
| `react/pirobot/src/VideoStreamControl.test.js` | **Create** — renders without size props |
| `react/pirobot/src/ArmControl.js` | **Modify** — slider `style={{width:150}}` → `sx={{width:'100%'}}` |
| `react/pirobot/src/DirectionCross.js` | **Modify** — fix invalid inline style key |
| `react/pirobot/src/ArmControl.test.js` | **Create** — renders sliders |
| `react/pirobot/src/home.js` | **Modify** — remove resize state, responsive layout, toolbar overflow menu |
| `react/pirobot/src/home.test.js` | **Create** — overflow menu toggle |

---

## Task 1: ResponsiveJoystick component

**Files:**
- Create: `react/pirobot/src/ResponsiveJoystick.js`
- Create: `react/pirobot/src/ResponsiveJoystick.test.js`

- [ ] **Step 1: Write the failing test**

```jsx
// react/pirobot/src/ResponsiveJoystick.test.js
import React from 'react';
import { render, screen } from '@testing-library/react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import useMediaQuery from '@mui/material/useMediaQuery';
import ResponsiveJoystick from './ResponsiveJoystick';

jest.mock('react-joystick-component', () => ({
  Joystick: ({ size, stickSize }) => (
    <div data-testid="joystick" data-size={String(size)} data-stick-size={String(stickSize)} />
  ),
}));

jest.mock('@mui/material/useMediaQuery', () => jest.fn());

const theme = createTheme();
const wrap = (ui) => render(<ThemeProvider theme={theme}>{ui}</ThemeProvider>);

test('uses size 80 on xs (portrait mobile)', () => {
  // first call: down('sm') = true (is xs), second call: between('sm','md') = false
  useMediaQuery.mockReturnValueOnce(true).mockReturnValueOnce(false);
  wrap(<ResponsiveJoystick move={() => {}} stop={() => {}} />);
  expect(screen.getByTestId('joystick')).toHaveAttribute('data-size', '80');
  expect(screen.getByTestId('joystick')).toHaveAttribute('data-stick-size', '36');
});

test('uses size 100 on sm (tablet/landscape)', () => {
  // first call: down('sm') = false, second call: between('sm','md') = true
  useMediaQuery.mockReturnValueOnce(false).mockReturnValueOnce(true);
  wrap(<ResponsiveJoystick move={() => {}} stop={() => {}} />);
  expect(screen.getByTestId('joystick')).toHaveAttribute('data-size', '100');
  expect(screen.getByTestId('joystick')).toHaveAttribute('data-stick-size', '45');
});

test('uses size 120 on desktop', () => {
  // neither xs nor sm
  useMediaQuery.mockReturnValue(false);
  wrap(<ResponsiveJoystick move={() => {}} stop={() => {}} />);
  expect(screen.getByTestId('joystick')).toHaveAttribute('data-size', '120');
  expect(screen.getByTestId('joystick')).toHaveAttribute('data-stick-size', '54');
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd react/pirobot && npm test -- --testPathPattern=ResponsiveJoystick --watchAll=false
```

Expected: FAIL — `Cannot find module './ResponsiveJoystick'`

- [ ] **Step 3: Implement ResponsiveJoystick**

```jsx
// react/pirobot/src/ResponsiveJoystick.js
import React from 'react';
import { useTheme } from '@mui/material/styles';
import useMediaQuery from '@mui/material/useMediaQuery';
import { Joystick } from 'react-joystick-component';

export default function ResponsiveJoystick(props) {
  const theme = useTheme();
  const isXs = useMediaQuery(theme.breakpoints.down('sm'));
  const isSm = useMediaQuery(theme.breakpoints.between('sm', 'md'));
  const size = isXs ? 80 : isSm ? 100 : 120;
  const stickSize = Math.round(size * 0.45);
  return (
    <Joystick
      size={size}
      stickSize={stickSize}
      sticky={false}
      baseColor="grey"
      stickColor="black"
      minDistance={2}
      {...props}
    />
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd react/pirobot && npm test -- --testPathPattern=ResponsiveJoystick --watchAll=false
```

Expected: PASS — 3 tests passing

- [ ] **Step 5: Commit**

```bash
git add react/pirobot/src/ResponsiveJoystick.js react/pirobot/src/ResponsiveJoystick.test.js
git commit -m "feat: add ResponsiveJoystick with breakpoint-aware sizing"
```

---

## Task 2: VideoStreamControl — CSS sizing

**Files:**
- Modify: `react/pirobot/src/VideoStreamControl.js`
- Create: `react/pirobot/src/VideoStreamControl.test.js`

- [ ] **Step 1: Write the failing test**

```jsx
// react/pirobot/src/VideoStreamControl.test.js
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd react/pirobot && npm test -- --testPathPattern=VideoStreamControl --watchAll=false
```

Expected: FAIL — img has `maxHeight` / `maxWidth` styles, not `width: 100%`

- [ ] **Step 3: Update VideoStreamControl render method**

In `react/pirobot/src/VideoStreamControl.js`, replace the `render()` method:

```jsx
render() {
  let base64String = "";
  if (this.state.frame !== null) {
    var binary = '';
    var bytes = new Uint8Array(this.state.frame);
    var len = bytes.byteLength;
    for (var i = 0; i < len; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    base64String = btoa(binary);
  }
  let source = "logo512.png";
  if (base64String !== null) {
    source = `data:image/jpg;base64,${base64String}`;
  }
  return (
    <img
      src={source}
      style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
      alt="Camera Feed"
      onMouseMove={this.props.onMouseMove}
      onClick={this.props.onClick}
    />
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd react/pirobot && npm test -- --testPathPattern=VideoStreamControl --watchAll=false
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add react/pirobot/src/VideoStreamControl.js react/pirobot/src/VideoStreamControl.test.js
git commit -m "feat: VideoStreamControl fills container via CSS instead of pixel props"
```

---

## Task 3: ArmControl + DirectionCross fixes

**Files:**
- Modify: `react/pirobot/src/ArmControl.js`
- Modify: `react/pirobot/src/DirectionCross.js`
- Create: `react/pirobot/src/ArmControl.test.js`

- [ ] **Step 1: Write the failing test**

```jsx
// react/pirobot/src/ArmControl.test.js
import React from 'react';
import { render, screen } from '@testing-library/react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import ArmControl from './ArmControl';

const theme = createTheme();

const status = {
  config: {
    shoulder: { max_angle: 180 },
    forearm:  { max_angle: 180 },
    wrist:    { max_angle: 180 },
    claw:     { max_angle: 180 },
  },
  position: { shoulder: 0, forearm: 0, wrist: 0, claw: 0 },
};

test('renders sliders without fixed pixel widths', () => {
  const { container } = render(
    <ThemeProvider theme={theme}>
      <ArmControl enabled={true} status={status} move={() => {}} stop={() => {}} move_limb={() => {}} />
    </ThemeProvider>
  );
  const sliders = container.querySelectorAll('.MuiSlider-root');
  sliders.forEach((slider) => {
    expect(slider).not.toHaveStyle({ width: '150px' });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd react/pirobot && npm test -- --testPathPattern=ArmControl --watchAll=false
```

Expected: FAIL — sliders have `width: 150px`

- [ ] **Step 3: Fix ArmControl sliders**

In `react/pirobot/src/ArmControl.js`, replace `style={{width: 150}}` with `sx={{width: '100%'}}` in both `relative_slider` and `absolute_slider`:

```jsx
relative_slider = (props) => {
  return (
    <Slider
      min={-100}
      max={100}
      step={1}
      aria-label={props["aria-label"]}
      orientation="horizontal"
      sx={{ width: '100%' }}
      value={this.state[props.servo + "_slider_position"]}
      onChange={this.move_arm.bind(this, props.servo)}
      onChangeCommitted={this.stop_arm.bind(this, props.servo)}
      marks={[{value: 0}]}
    />
  )
}

absolute_slider = (props) => {
  return (
    <Slider
      color="success"
      min={0}
      max={this.props.status.config[props.servo].max_angle}
      step={1}
      aria-label={props["aria-label"]}
      orientation="horizontal"
      valueLabelDisplay="auto"
      sx={{ width: '100%' }}
      value={this.props.status.position[props.servo]}
      onChange={this.move_arm_limb.bind(this, props.servo)}
      marks={[{value: 0}]}
    />
  )
}
```

- [ ] **Step 4: Fix DirectionCross invalid style key**

In `react/pirobot/src/DirectionCross.js`, replace the `button` render method:

```jsx
button = (props) => {
  return (
    <IconButton
      onMouseUp={this.props.stop}
      onTouchEnd={this.props.stop}
      onMouseDown={this.props.move.bind(null, props.left_speed, props.right_speed)}
      onTouchStart={this.props.move.bind(null, props.left_speed, props.right_speed)}
      sx={{ bgcolor: 'grey' }}
    >
      {props.children}
    </IconButton>
  )
}
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd react/pirobot && npm test -- --testPathPattern=ArmControl --watchAll=false
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add react/pirobot/src/ArmControl.js react/pirobot/src/ArmControl.test.js react/pirobot/src/DirectionCross.js
git commit -m "fix: ArmControl sliders fluid width, DirectionCross valid style prop"
```

---

## Task 4: home.js — remove resize state, new outer container

**Files:**
- Modify: `react/pirobot/src/home.js`

- [ ] **Step 1: Add Box import if not present**

At the top of `react/pirobot/src/home.js`, verify `Box` is already imported from `@mui/material/Box` (it is). Also add these imports:

```jsx
import Collapse from '@mui/material/Collapse';
import Typography from '@mui/material/Typography';
import MoreHorizIcon from '@mui/icons-material/MoreHoriz';
import ResponsiveJoystick from './ResponsiveJoystick';
```

- [ ] **Step 2: Remove resize state and listener**

In the constructor, change the state initializer — remove `window_height` and `window_width`, add `overflowOpen`:

```jsx
this.state = {
  ws: null,
  fps: 0,
  robot_config: {},
  robot_name: null,
  robot_status: {},
  control: "joystick",
  control_arm: false,
  drive_slow_mode: false,
  overflowOpen: false,
};
```

Delete the `handleWindowResize` method entirely:

```jsx
// DELETE this method:
// handleWindowResize = () => {
//   this.setState({window_height: window.innerHeight, window_width: window.innerWidth});
// }
```

In `componentDidMount`, remove the resize listener line:

```jsx
componentDidMount() {
  this.connect();
  // removed: window.addEventListener('resize', this.handleWindowResize);
}
```

- [ ] **Step 3: Replace the outer container in render()**

Replace:
```jsx
<div className="App" style={{display: this.state.window_height > 400 ? "flex" : "block"}}>
```
With:
```jsx
<Box sx={{
  position: { xs: 'fixed', md: 'static' },
  top: { xs: 0 }, left: { xs: 0 }, right: { xs: 0 }, bottom: { xs: 0 },
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
}}>
```

Replace the closing `</div>` with `</Box>`.

- [ ] **Step 4: Verify the app still starts**

```bash
cd react/pirobot && npm start
```

Open http://localhost:3000 — page should load without console errors. Ctrl+C to stop.

- [ ] **Step 5: Commit**

```bash
git add react/pirobot/src/home.js
git commit -m "refactor: remove JS resize listener, responsive outer container"
```

---

## Task 5: home.js — responsive body layout

**Files:**
- Modify: `react/pirobot/src/home.js`

Replace the entire inner content of the outer Box (everything between the outer `<Box>` tags) with this structure. The desktop toolbar and 3-column body use `display: { xs: 'none', md: 'flex' }`; the video is always rendered once in the center; mobile overlays use `display: { xs: ..., md: 'none' }`.

- [ ] **Step 1: Replace the Grid container with a flex column structure**

Replace everything inside the outer `<Box>` with:

```jsx
{/* ── DESKTOP: toolbar (hidden on mobile) ── */}
<Box sx={{ display: { xs: 'none', md: 'flex' }, flexWrap: 'wrap', width: 'fit-content',
    bgcolor: 'grey', border: (theme) => `1px solid ${theme.palette.divider}`, borderRadius: 1 }}>
  <Tooltip title="Open photo gallery"><IconButton component={Link} to="/pictures"><PhotoLibraryIcon/></IconButton></Tooltip>
  <Tooltip title="Open video gallery"><IconButton component={Link} to="/videos"><VideoLibraryIcon/></IconButton></Tooltip>
  <Tooltip title="Robot Settings"><IconButton component={Link} to="/settings"><SettingsIcon/></IconButton></Tooltip>
  <Divider orientation="vertical" flexItem/>
  {this.state.robot_config.robot_has_back_camera && <IconButton onClick={this.toogleCamera}><SwitchCameraIcon/></IconButton>}
  {this.state.robot_config.robot_has_back_camera && <IconButton onClick={this.send_action.bind(this, "camera", "toggle_overlay", {})}><PictureInPictureIcon/></IconButton>}
  <Tooltip title="Record a Video"><IconButton onClick={this.send_action.bind(this, "camera", "start_video", {})}><FiberManualRecordIcon/></IconButton></Tooltip>
  <Tooltip title="Stop Video Recording"><IconButton onClick={this.send_action.bind(this, "camera", "stop_video", {})}><StopIcon/></IconButton></Tooltip>
  <Tooltip title="Take a Photo"><IconButton onClick={this.send_action.bind(this, "camera", "capture_picture", {})}><CameraAltIcon/></IconButton></Tooltip>
  <Divider orientation="vertical" flexItem/>
  {this.state.control === "joystick" && <Tooltip title="Use D-pad"><IconButton onClick={this.toggleControl}><GamepadIcon/></IconButton></Tooltip>}
  {this.state.control === "cross"   && <Tooltip title="Use Joystick"><IconButton onClick={this.toggleControl}><ControlCameraIcon/></IconButton></Tooltip>}
  {this.state.robot_config.robot_has_arm && <Tooltip title="Toggle Arm Control"><IconButton onClick={this.toggleArmControl}><PrecisionManufacturingIcon/></IconButton></Tooltip>}
  <Divider orientation="vertical" flexItem/>
  {this.state.robot_config.robot_has_light && <Tooltip title="Front Lights"><IconButton onClick={this.send_action.bind(this, "light", "toggle", {})}>{this.state.robot_status.light?.left_on ? <FlashlightOffIcon/> : <FlashlightOnIcon/>}</IconButton></Tooltip>}
  {this.state.robot_config.robot_has_light && this.state.robot_config.robot_has_arm && <Tooltip title="Arm Lights"><IconButton onClick={this.send_action.bind(this, "light", "toggle_arm_light", {})}>{this.state.robot_status.light?.arm_on ? <FlashlightOffIcon/> : <FlashlightOnIcon/>}</IconButton></Tooltip>}
  {this.state.robot_config.robot_has_light && <Divider orientation="vertical" flexItem/>}
  <Tooltip title="Face Recognition"><IconButton onClick={this.send_action.bind(this, "face_detection", "toggle", {})}>{this.face_detection ? <FaceRetouchingOffIcon/> : <FaceIcon/>}</IconButton></Tooltip>
  <Tooltip title="Start Patrolling"><IconButton onClick={this.send_action.bind(this, "drive", "patrol", {})}><RadarIcon/></IconButton></Tooltip>
  <Tooltip title="Stop Robot"><IconButton onClick={this.send_action.bind(this, "drive", "stop", {})}><DangerousIcon/></IconButton></Tooltip>
</Box>

{/* ── BODY ROW: fills remaining height, position:relative for mobile overlays ── */}
<Box sx={{ flex: 1, display: 'flex', minHeight: 0, position: 'relative' }}>

  {/* LEFT column: joystick/dpad/arm — desktop only */}
  <Box sx={{ display: { xs: 'none', md: 'flex' }, width: '16.67%', alignItems: 'center', justifyContent: 'center' }}>
    <div style={{ display: (this.state.control === "joystick" && !this.state.control_arm) ? "block" : "none" }}>
      <ResponsiveJoystick move={this.handleJoystickMove} stop={this.handleStopRobot} />
    </div>
    <div style={{ paddingLeft: 5, display: (this.state.control === "cross" && !this.state.control_arm) ? "block" : "none" }}>
      <DirectionCross move={this.handleMoveRobot} stop={this.handleStopRobot} />
    </div>
    <div style={{ paddingLeft: 5, display: this.state.control_arm ? "block" : "none" }}>
      <ArmControl
        move={this.move_arm} stop={this.stop_arm} move_limb={this.move_arm_limb}
        enabled={this.state.robot_config.robot_has_arm} status={this.state.robot_status.arm}
      />
    </div>
  </Box>

  {/* CENTER: video — always rendered, full width on mobile */}
  <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', minWidth: 0 }}>
    <VideoStreamControl updateFps={this.updateFps} />
  </Box>

  {/* RIGHT column: camera servo slider — desktop only */}
  <Box sx={{ display: { xs: 'none', md: 'flex' }, width: '16.67%', alignItems: 'center', justifyContent: 'center' }}>
    {this.state.robot_config.robot_has_camera_servo && (
      <Stack spacing={2} justifyContent="center" alignItems="center" direction="column">
        <Slider
          min={0} max={100} step={1}
          style={{ height: 200 }}
          aria-label="Camera position"
          orientation="vertical"
          valueLabelDisplay="auto"
          value={this.state.robot_status.camera?.position}
          onChange={this.set_camera_position}
          marks={[{ value: this.state.robot_status.camera?.center_position }]}
        />
        <IconButton onClick={this.center_camera_position}><VerticalAlignCenterIcon/></IconButton>
      </Stack>
    )}
  </Box>

  {/* ── MOBILE OVERLAYS (position:absolute, hidden on desktop) ── */}

  {/* Mobile: floating toolbar pill */}
  <Box sx={{
    display: { xs: 'flex', md: 'none' },
    position: 'absolute', top: 8, left: 8, right: 8, zIndex: 10,
    bgcolor: 'rgba(30,30,30,0.88)', borderRadius: '20px', px: 1, py: 0.5,
    alignItems: 'center', gap: 0.5,
  }}>
    <Tooltip title="Stop Robot">
      <IconButton onClick={this.send_action.bind(this, "drive", "stop", {})} sx={{ color: '#e53935' }}>
        <DangerousIcon/>
      </IconButton>
    </Tooltip>
    <Divider orientation="vertical" flexItem sx={{ borderColor: 'rgba(255,255,255,0.15)' }}/>
    <Tooltip title="Record a Video"><IconButton onClick={this.send_action.bind(this, "camera", "start_video", {})}><FiberManualRecordIcon/></IconButton></Tooltip>
    <Tooltip title="Stop Recording"><IconButton onClick={this.send_action.bind(this, "camera", "stop_video", {})}><StopIcon/></IconButton></Tooltip>
    <Tooltip title="Take a Photo"><IconButton onClick={this.send_action.bind(this, "camera", "capture_picture", {})}><CameraAltIcon/></IconButton></Tooltip>
    <Divider orientation="vertical" flexItem sx={{ borderColor: 'rgba(255,255,255,0.15)' }}/>
    {this.state.control === "joystick" && <Tooltip title="Use D-pad"><IconButton onClick={this.toggleControl}><GamepadIcon/></IconButton></Tooltip>}
    {this.state.control === "cross"   && <Tooltip title="Use Joystick"><IconButton onClick={this.toggleControl}><ControlCameraIcon/></IconButton></Tooltip>}
    {this.state.robot_config.robot_has_arm && <Tooltip title="Toggle Arm Control"><IconButton onClick={this.toggleArmControl}><PrecisionManufacturingIcon/></IconButton></Tooltip>}
    <Box sx={{ flex: 1 }}/>
    <IconButton aria-label="More actions" onClick={() => this.setState({ overflowOpen: !this.state.overflowOpen })}>
      <MoreHorizIcon/>
    </IconButton>
  </Box>

  {/* Mobile: overflow menu (slides down from toolbar) */}
  <Collapse in={this.state.overflowOpen} sx={{ display: { xs: 'block', md: 'none' }, position: 'absolute', top: 56, left: 8, right: 8, zIndex: 10 }}>
    <Box sx={{ bgcolor: 'rgba(30,30,30,0.92)', borderRadius: 2, p: 1, display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
      <Tooltip title="Open photo gallery"><IconButton component={Link} to="/pictures"><PhotoLibraryIcon/></IconButton></Tooltip>
      <Tooltip title="Open video gallery"><IconButton component={Link} to="/videos"><VideoLibraryIcon/></IconButton></Tooltip>
      <Tooltip title="Robot Settings"><IconButton component={Link} to="/settings"><SettingsIcon/></IconButton></Tooltip>
      {this.state.robot_config.robot_has_back_camera && <Tooltip title="Switch Camera"><IconButton onClick={this.toogleCamera}><SwitchCameraIcon/></IconButton></Tooltip>}
      {this.state.robot_config.robot_has_back_camera && <Tooltip title="Picture in Picture"><IconButton onClick={this.send_action.bind(this, "camera", "toggle_overlay", {})}><PictureInPictureIcon/></IconButton></Tooltip>}
      {this.state.robot_config.robot_has_light && <Tooltip title="Front Lights"><IconButton onClick={this.send_action.bind(this, "light", "toggle", {})}>{this.state.robot_status.light?.left_on ? <FlashlightOffIcon/> : <FlashlightOnIcon/>}</IconButton></Tooltip>}
      {this.state.robot_config.robot_has_light && this.state.robot_config.robot_has_arm && <Tooltip title="Arm Lights"><IconButton onClick={this.send_action.bind(this, "light", "toggle_arm_light", {})}>{this.state.robot_status.light?.arm_on ? <FlashlightOffIcon/> : <FlashlightOnIcon/>}</IconButton></Tooltip>}
      <Tooltip title="Face Recognition"><IconButton onClick={this.send_action.bind(this, "face_detection", "toggle", {})}>{this.face_detection ? <FaceRetouchingOffIcon/> : <FaceIcon/>}</IconButton></Tooltip>
      <Tooltip title="Start Patrolling"><IconButton onClick={this.send_action.bind(this, "drive", "patrol", {})}><RadarIcon/></IconButton></Tooltip>
    </Box>
  </Collapse>

  {/* Mobile: floating joystick/dpad/arm — bottom left */}
  <Box sx={{ display: { xs: 'block', md: 'none' }, position: 'absolute', bottom: 16, left: 16, zIndex: 10 }}>
    <div style={{ display: (this.state.control === "joystick" && !this.state.control_arm) ? "block" : "none" }}>
      <ResponsiveJoystick move={this.handleJoystickMove} stop={this.handleStopRobot} />
    </div>
    <div style={{ display: (this.state.control === "cross" && !this.state.control_arm) ? "block" : "none" }}>
      <DirectionCross move={this.handleMoveRobot} stop={this.handleStopRobot} />
    </div>
    <div style={{ display: this.state.control_arm ? "block" : "none" }}>
      <ArmControl
        move={this.move_arm} stop={this.stop_arm} move_limb={this.move_arm_limb}
        enabled={this.state.robot_config.robot_has_arm} status={this.state.robot_status.arm}
      />
    </div>
  </Box>

  {/* Mobile: camera servo slider — right edge */}
  {this.state.robot_config.robot_has_camera_servo && (
    <Box sx={{ display: { xs: 'flex', md: 'none' }, position: 'absolute', right: 8, top: 56, bottom: 80, zIndex: 10, flexDirection: 'column', alignItems: 'center' }}>
      <Slider
        min={0} max={100} step={1}
        sx={{ flex: 1 }}
        aria-label="Camera position"
        orientation="vertical"
        valueLabelDisplay="auto"
        value={this.state.robot_status.camera?.position}
        onChange={this.set_camera_position}
        marks={[{ value: this.state.robot_status.camera?.center_position }]}
      />
      <IconButton onClick={this.center_camera_position}><VerticalAlignCenterIcon/></IconButton>
    </Box>
  )}

  {/* Mobile: FPS badge — bottom right */}
  <Typography variant="caption" sx={{
    display: { xs: 'block', md: 'none' },
    position: 'absolute', bottom: 8, right: 8, zIndex: 10,
    color: 'rgba(255,255,255,0.5)', bgcolor: 'rgba(0,0,0,0.5)', borderRadius: 1, px: 1,
  }}>
    {this.state.fps} FPS
  </Typography>

</Box>

{/* ── STATUS BAR: desktop only ── */}
<Box sx={{ display: { xs: 'none', md: 'block' } }}>
  <p style={{ margin: 0, padding: 0, fontSize: '15px' }}>
    Connected to {this.state.robot_name} - {this.state.fps} FPS
  </p>
</Box>
```

- [ ] **Step 2: Verify the app renders on desktop**

```bash
cd react/pirobot && npm start
```

Open http://localhost:3000. On desktop (≥ 960px wide): full toolbar visible, 3-column body. Resize window to narrow: toolbar wraps, layout stays. Ctrl+C.

- [ ] **Step 3: Verify the app renders on mobile**

In browser DevTools, toggle device toolbar (Ctrl+Shift+M), select a phone (e.g. iPhone 12, 390×844). Verify:
- Video fills screen
- Floating toolbar pill visible at top
- Joystick floating bottom-left
- FPS badge bottom-right
- No horizontal scroll

- [ ] **Step 4: Commit**

```bash
git add react/pirobot/src/home.js
git commit -m "feat: responsive layout — full-screen overlay on mobile, 3-column on desktop"
```

---

## Task 6: home.js — toolbar overflow menu test

**Files:**
- Create: `react/pirobot/src/home.test.js`

- [ ] **Step 1: Write the test**

```jsx
// react/pirobot/src/home.test.js
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import { MemoryRouter } from 'react-router-dom';
import Home from './home';

// suppress WebSocket
global.WebSocket = class {
  constructor() { this.onopen = null; this.onmessage = null; this.onclose = null; this.onerror = null; }
  send() {}
  close() {}
};

// suppress Joystick canvas errors
jest.mock('./ResponsiveJoystick', () => () => <div data-testid="joystick" />);

const theme = createTheme();
const wrap = (ui) => render(
  <ThemeProvider theme={theme}><MemoryRouter>{ui}</MemoryRouter></ThemeProvider>
);

test('overflow menu button is present', () => {
  wrap(<Home />);
  expect(screen.getByLabelText('More actions')).toBeInTheDocument();
});

test('overflow menu opens when more button is clicked', () => {
  wrap(<Home />);
  fireEvent.click(screen.getByLabelText('More actions'));
  // After clicking, overflowOpen=true — the Collapse renders its children into the DOM
  expect(screen.getAllByTitle('Open photo gallery').length).toBeGreaterThan(0);
});
```

- [ ] **Step 2: Run test**

```bash
cd react/pirobot && npm test -- --testPathPattern=home.test --watchAll=false
```

Expected: PASS — 2 tests passing

- [ ] **Step 3: Commit**

```bash
git add react/pirobot/src/home.test.js
git commit -m "test: overflow menu toggle in Home"
```

---

## Task 7: Run all tests and verify build

- [ ] **Step 1: Run the full test suite**

```bash
cd react/pirobot && npm test -- --watchAll=false
```

Expected: All tests PASS. Fix any failures before proceeding.

- [ ] **Step 2: Build production bundle**

```bash
cd react/pirobot && npm run build
```

Expected: `Compiled successfully.` with no errors.

- [ ] **Step 3: Final visual check**

```bash
cd react/pirobot && npm start
```

Check these four cases in browser DevTools:
1. **Desktop (1280px wide):** Full toolbar, 3-column body, status bar at bottom
2. **Tablet landscape (768px wide):** Same 3-column, toolbar wraps at narrow widths
3. **Phone landscape (667px wide):** 3-column tighter, overflow menu appears on mobile pill
4. **Phone portrait (390px wide):** Full-screen video, floating toolbar + joystick overlays

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: responsive layout complete — all screen sizes"
```
