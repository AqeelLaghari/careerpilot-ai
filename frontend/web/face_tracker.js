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

  let stream = null, video = null, box = null, landmarker = null, loop = null;
  let sample = { status: "off" };
  let frames = 0, fpsStart = 0, fps = 0, lastRun = 0;

  function makeBox() {
    if (box) return box;
    box = document.createElement("div");
    box.style.cssText = "width:100%;height:100%;background:#000;overflow:hidden;border-radius:12px;";
    video = document.createElement("video");
    video.setAttribute("playsinline", "");
    video.muted = true;
    video.autoplay = true;
    // mirror it, like a selfie camera; measurements are converted to the same view
    video.style.cssText = "width:100%;height:100%;object-fit:cover;transform:scaleX(-1);";
    box.appendChild(video);
    return box;
  }

  async function start() {
    makeBox();
    if (stream) return "ok";
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" }, audio: false,
      });
      video.srcObject = stream;
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

  function measure(result, now) {
    frames++;
    if (now - fpsStart >= 1000) {
      fps = Math.round((frames * 1000) / (now - fpsStart));
      frames = 0;
      fpsStart = now;
    }
    const faces = result.faceLandmarks || [];
    if (!faces.length) {
      sample = { status: "ready", face: false, faces: 0, fps, t: Date.now() };
      return;
    }
    const lm = faces[0];
    let h = 0, v = 0, open = 0;
    for (const e of EYES) {
      // corners sorted left->right in the camera image, so both eyes are measured the same way
      let [a, b] = e.corners.map((i) => lm[i]);
      if (a.x > b.x) [a, b] = [b, a];
      h += along(lm[e.iris], a, b);
      const up = lm[e.lids[0]], down = lm[e.lids[1]];
      v += along(lm[e.iris], up, down);
      open += Math.hypot(down.x - up.x, down.y - up.y) / (Math.hypot(b.x - a.x, b.y - a.y) || 1e-6);
    }
    h /= 2; v /= 2; open /= 2;
    // camera image -> mirror view: moving right in the image = the user's left
    const gazeH = -(h - 0.5) * 2;
    const gazeV = (v - 0.5) * 2;
    const nose = lm[NOSE], ca = lm[CHEEK_A], cb = lm[CHEEK_B];
    const left = ca.x < cb.x ? ca : cb, right = ca.x < cb.x ? cb : ca;
    const yaw = -(along(nose, left, right) - 0.5) * 2;
    const pitch = (along(nose, lm[BROW_MID], lm[CHIN]) - 0.45) * 2;
    const r = (x) => Math.round(x * 1000) / 1000;
    sample = {
      status: "ready", face: true, faces: faces.length, fps, t: Date.now(),
      gaze_h: r(gazeH), gaze_v: r(gazeV), head_yaw: r(yaw), head_pitch: r(pitch), eyes_open: r(open),
    };
  }

  function stop() {
    if (loop) cancelAnimationFrame(loop);
    loop = null;
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
    if (video) video.srcObject = null;
    sample = { status: "off" };
  }

  window.cpCamera = {
    start, track, stop,
    container: () => makeBox(),
    latest: () => JSON.stringify(sample),
  };
})();
