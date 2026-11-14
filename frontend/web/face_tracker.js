// CareerPilot AI: camera + face tracking for the live interview (Day 18).
//
// Runs entirely in the browser. The video is NEVER uploaded: MediaPipe Face Landmarker
// (free, by Google) finds 478 face points (including both irises) many times a second,
// and only small numbers are handed to the Flutter app.
//
// Flutter uses it through window.cpCamera:
//   start()        -> Promise<"ok" | error name>   ask for the camera and show it
//   container()    -> the <div> holding the live <video> (shown by Flutter's HtmlElementView)
//   track()        -> Promise<"ok" | error>        load MediaPipe and start tracking
//   latest()       -> JSON string with the newest measurements (see `sample` below)
//   stop()         -> turn the camera off
//
// Measurements are from the USER's point of view (as in a mirror):
//   gaze_h  -1 = eyes turned to the user's left,  +1 = to the right, 0 = straight
//   gaze_v  -1 = eyes up,                          +1 = down
//   head_yaw   -1 = head turned to the left ... +1 = right  (nose position between the cheeks)
//   head_pitch -1 = head up ... +1 = head down             (nose position between eyes and chin)
//   eyes_open  eyelid opening / eye width (about 0.25-0.35 open, under ~0.12 closed or blinking)
(function () {
  const VISION = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";
  const MODEL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";
  const TARGET_FPS = 15;

  // Landmark numbers in the MediaPipe face mesh (478 points with irises)
  const EYES = [
    { corners: [33, 133], lids: [159, 145], iris: 468 },
    { corners: [362, 263], lids: [386, 374], iris: 473 },
  ];
  const NOSE = 1, CHEEK_A = 234, CHEEK_B = 454, BROW_MID = 168, CHIN = 152;

  // `video` is the HIDDEN video MediaPipe reads; it stays in one place for the whole session.
  // Every camera picture on screen is its OWN <video> showing the same camera stream (like two
  // TVs on one channel). Nothing is ever moved between screens: Chrome freezes a <video> that
  // is moved to another place on the page (the lobby -> full-screen interview bug).
  let stream = null, video = null, landmarker = null, loop = null;
  const shown = new Set();                       // on-screen <video> elements
  let sample = { status: "off" };
  let frames = 0, fpsStart = 0, fps = 0, lastRun = 0;

  function keepPlaying(v) {
    v.muted = true;
    v.autoplay = true;
    v.setAttribute("playsinline", "");
    v.addEventListener("pause", () => {
      if (stream) [0, 150, 500].forEach((ms) => setTimeout(() => {
        if (stream && v.paused) v.play().catch(() => {});
      }, ms));
    });
  }

  function trackerVideo() {
    if (video) return video;
    video = document.createElement("video");
    keepPlaying(video);
    // on the page (so the browser keeps decoding it) but invisible and not clickable
    video.style.cssText = "position:fixed;left:0;top:0;width:4px;height:3px;opacity:0.01;pointer-events:none;z-index:-1;";
    document.body.appendChild(video);
    return video;
  }

  function attach(v) {
    if (stream && v.srcObject !== stream) v.srcObject = stream;
    if (stream) v.play().catch(() => {});
  }

  // A new on-screen camera picture (Flutter asks for one per camera view).
  function container() {
    for (const v of shown) if (!v.isConnected && v.dataset.used) shown.delete(v);   // old screens
    const box = document.createElement("div");
    box.style.cssText = "width:100%;height:100%;background:#000;overflow:hidden;border-radius:12px;";
    const v = document.createElement("video");
    keepPlaying(v);
    // mirror it, like a selfie camera; measurements are converted to the same view
    v.style.cssText = "width:100%;height:100%;object-fit:cover;transform:scaleX(-1);";
    box.appendChild(v);
    shown.add(v);
    // start playing once Flutter has put it on the page
    attach(v);
    let tries = 0;
    const wait = setInterval(() => {
      if (v.isConnected) { v.dataset.used = "1"; attach(v); clearInterval(wait); }
      else if (++tries > 50) clearInterval(wait);              // 10 s
    }, 200);
    return box;
  }

  async function start() {
    trackerVideo();
    if (stream) return "ok";
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" }, audio: false,
      });
      attach(video);
      shown.forEach(attach);
      await video.play().catch(() => {});
      // If the camera is unplugged or blocked later, say so
      stream.getVideoTracks()[0].addEventListener("ended", () => { sample = { status: "camera_ended" }; });
      sample = { status: "camera_on" };
      return "ok";
    } catch (e) {
      sample = { status: "error", error: e.name || String(e) };
      return e.name || "error";
    }
  }

  async function track() {
    if (!stream) return "no_camera";
    if (!landmarker) {
      sample = { status: "loading" };
      try {
        const vision = await import(VISION + "/vision_bundle.mjs");
        const files = await vision.FilesetResolver.forVisionTasks(VISION + "/wasm");
        const opts = (delegate) => ({
          baseOptions: { modelAssetPath: MODEL, delegate },
          runningMode: "VIDEO", numFaces: 2,
        });
        try {
          landmarker = await vision.FaceLandmarker.createFromOptions(files, opts("GPU"));
        } catch (_) {
          landmarker = await vision.FaceLandmarker.createFromOptions(files, opts("CPU"));
        }
      } catch (e) {
        sample = { status: "error", error: "Face tracking could not load: " + (e.message || e) };
        return "error";
      }
    }
    if (!loop) {
      fpsStart = performance.now();
      const tick = () => {
        loop = requestAnimationFrame(tick);
        const now = performance.now();
        if (now - lastRun < 1000 / TARGET_FPS || video.readyState < 2) return;
        lastRun = now;
        try {
          measure(landmarker.detectForVideo(video, now), now);
        } catch (e) {
          sample = { status: "error", error: String(e) };
        }
      };
      loop = requestAnimationFrame(tick);
    }
    return "ok";
  }

  // Position of point p along the line a->b: 0 at a, 1 at b
  function along(p, a, b) {
    const dx = b.x - a.x, dy = b.y - a.y;
    const len2 = dx * dx + dy * dy || 1e-6;
    return ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2;
  }

  // ---- calibration: the user's normal "looking at the screen" position becomes the centre.
  // A laptop camera sits below the screen, so looking at the screen already reads as
  // "a bit down"; without this, up/down would be off for most people.
  // Sensitivity: how much raw change moves a value from the centre to the end (+-1).
  const SCALE = { h: 2.0, v: 9.0, open: 4.0, yaw: 2.0, pitch: 4.0 };
  let base = null, calib = null;                 // calib = samples being collected

  function calibrate(ms) {
    calib = { until: performance.now() + (ms || 1500), rows: [] };
  }

  // Live interview: while the interviewer is speaking the user listens and looks at the screen,
  // so the MIDDLE value (median) of that time becomes "straight ahead" for the next answer.
  // Re-measured every question, so a bad first calibration (leaning in to click Start, a low
  // laptop camera) is corrected; the median ignores short glances while listening.
  let listen = null;
  const median = (xs) => {
    const s = [...xs].sort((a, b) => a - b), n = s.length;
    return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
  };

  function baselineStart() { listen = []; }

  function baselineEnd() {
    const rows = listen || [];
    listen = null;
    if (rows.length < 8) return 0;                 // under ~0.5 s of a clear face: keep the old one
    base = {};
    for (const k of ["h", "v", "open", "yaw", "pitch"]) base[k] = median(rows.map((r) => r[k]));
    calib = null;
    return rows.length;
  }

  function raw(lm) {
    let h = 0, v = 0, open = 0, width = 0;
    for (const e of EYES) {
      // corners sorted left->right in the camera image, so both eyes are measured the same way
      let [a, b] = e.corners.map((i) => lm[i]);
      if (a.x > b.x) [a, b] = [b, a];
      const iris = lm[e.iris];
      const w = Math.hypot(b.x - a.x, b.y - a.y) || 1e-6;
      h += along(iris, a, b);
      // up/down: how far the iris is from the line between the eye corners (corners don't
      // move with the gaze, eyelids do), as a share of the eye width; + = below the line
      const cross = ((b.x - a.x) * (iris.y - a.y) - (b.y - a.y) * (iris.x - a.x)) / w;
      v += cross / w;
      const up = lm[e.lids[0]], down = lm[e.lids[1]];
      open += Math.hypot(down.x - up.x, down.y - up.y) / w;
      width += w;
    }
    h /= 2; v /= 2; open /= 2;
    const nose = lm[NOSE], ca = lm[CHEEK_A], cb = lm[CHEEK_B];
    const left = ca.x < cb.x ? ca : cb, right = ca.x < cb.x ? cb : ca;
    // head up/down: nose tip below the line between the eyes, as a share of the eye distance
    const eyeL = lm[EYES[0].iris], eyeR = lm[EYES[1].iris];
    const eyeDist = Math.hypot(eyeR.x - eyeL.x, eyeR.y - eyeL.y) || 1e-6;
    const noseDrop = ((eyeR.x - eyeL.x) * (nose.y - eyeL.y) - (eyeR.y - eyeL.y) * (nose.x - eyeL.x)) / (eyeDist * eyeDist);
    return { h, v, open, yaw: along(nose, left, right), pitch: Math.abs(noseDrop) };
  }

  const clamp = (x) => Math.max(-1.5, Math.min(1.5, x));
  const r3 = (x) => Math.round(x * 1000) / 1000;

  function measure(result, now) {
    frames++;
    if (now - fpsStart >= 1000) {
      fps = Math.round((frames * 1000) / (now - fpsStart));
      frames = 0;
      fpsStart = now;
    }
    const faces = result.faceLandmarks || [];
    if (!faces.length) {
      sample = { status: "ready", face: false, faces: 0, fps, t: Date.now(), calibrated: !!base, calibrating: !!calib };
      return;
    }
    const m = raw(faces[0]);
    if (listen && faces.length === 1 && m.open > 0.12 && listen.length < 1500) listen.push(m);
    if (!base && !calib) calibrate(1500);          // first time a face is seen
    if (calib) {
      if (faces.length === 1 && m.open > 0.12) calib.rows.push(m);   // skip blinks
      if (now >= calib.until && calib.rows.length >= 5) {
        const avg = (k) => calib.rows.reduce((t, r) => t + r[k], 0) / calib.rows.length;
        base = { h: avg("h"), v: avg("v"), open: avg("open"), yaw: avg("yaw"), pitch: avg("pitch") };
        calib = null;
      } else if (now >= calib.until + 3000) {
        calib = null;                              // no clear face: try again next time
      }
    }
    const b = base || { h: 0.5, v: 0, open: m.open, yaw: 0.5, pitch: m.pitch };
    // camera image -> mirror view: moving right in the image = the user's left
    const gazeH = -(m.h - b.h) * SCALE.h * 2;
    // eyes down: iris drops below the corner line AND the eyelids close a little
    const gazeV = (m.v - b.v) * SCALE.v - (m.open - b.open) * SCALE.open;
    const yaw = -(m.yaw - b.yaw) * SCALE.yaw * 2;
    const pitch = (m.pitch - b.pitch) * SCALE.pitch;
    sample = {
      status: "ready", face: true, faces: faces.length, fps, t: Date.now(),
      calibrated: !!base, calibrating: !!calib,
      gaze_h: r3(clamp(gazeH)), gaze_v: r3(clamp(gazeV)), head_yaw: r3(clamp(yaw)),
      head_pitch: r3(clamp(pitch)), eyes_open: r3(m.open),
    };
  }

  function stop() {
    if (loop) cancelAnimationFrame(loop);
    loop = null;
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
    if (video) video.srcObject = null;
    shown.forEach((v) => { v.srcObject = null; });
    shown.clear();
    sample = { status: "off" };
  }

  window.cpCamera = {
    start, track, stop, container, baselineStart, baselineEnd,
    calibrate: () => { base = null; calibrate(1500); },
    latest: () => JSON.stringify(sample),
  };
})();
