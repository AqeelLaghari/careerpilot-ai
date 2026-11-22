import 'package:careerpilot/services/camera/face_math.dart';
import 'package:flutter_test/flutter_test.dart';

/// A simple face in camera-image pixels (not mirrored): eyes level, irises centred, nose in the middle.
/// [irisShift] moves both irises (pixels, + = right in the image), [noseShift] moves the nose,
/// [lidGap] is the eyelid opening.
Map<int, List<double>> facePixels({double irisShift = 0, double noseShift = 0, double lidGap = 9, double cx = 320}) {
  const y = 200.0;
  final l = cx - 50, r = cx + 50; // centres of the eyes in the image
  return {
    33: [l - 15, y],
    133: [l + 15, y],
    159: [l, y - lidGap / 2],
    145: [l, y + lidGap / 2],
    468: [l + irisShift, y],
    362: [r - 15, y],
    263: [r + 15, y],
    386: [r, y - lidGap / 2],
    374: [r, y + lidGap / 2],
    473: [r + irisShift, y],
    1: [cx + noseShift, y + 45],
    234: [cx - 85, y + 30],
    454: [cx + 85, y + 30],
  };
}

/// What FaceTracker.kt sends for a picture of [w] x [h] pixels.
Map<Object?, Object?> frame(Map<int, List<double>> px, {double w = 480, double h = 640, int faces = 1}) => {
  'faces': faces,
  'fps': 15,
  'w': w,
  'h': h,
  'pts': [
    for (final i in FaceMath.points) ...[px[i]![0] / w, px[i]![1] / h],
  ],
};

void main() {
  late double now;
  late FaceMath math;

  setUp(() {
    now = 0;
    math = FaceMath(clock: () => now);
  });

  /// Look straight for 2 s (15 checks a second) so the first calibration finishes.
  void calibrate() {
    for (var i = 0; i < 30; i++) {
      math.onEvent(frame(facePixels()));
      now += 1000 / 15;
    }
  }

  test('looking straight after calibration counts as looking at the screen', () {
    calibrate();
    final s = math.onEvent(frame(facePixels()));
    expect(s.calibrated, isTrue);
    expect(s.direction, 'Looking at the screen');
  });

  test('irises moved right in the camera image = eyes looking to the user\'s left (mirror view)', () {
    calibrate();
    final s = math.onEvent(frame(facePixels(irisShift: 6)));
    expect(s.gazeH, lessThan(-0.35));
    expect(s.direction, 'Eyes looking left');
  });

  test('nose moved right in the camera image = head turned to the user\'s left', () {
    calibrate();
    final s = math.onEvent(frame(facePixels(noseShift: 30)));
    expect(s.headYaw, lessThan(-0.45));
    expect(s.direction, 'Head turned left');
  });

  test('closed eyes are detected as blinking', () {
    calibrate();
    final s = math.onEvent(frame(facePixels(lidGap: 1)));
    expect(s.eyesOpen, lessThan(0.12));
    expect(s.direction, 'Eyes closed / blinking');
  });

  test('no face and more than one face', () {
    expect(math.onEvent({'faces': 0, 'fps': 15, 'w': 480, 'h': 640}).direction, 'No face in view');
    calibrate();
    expect(math.onEvent(frame(facePixels(), faces: 2)).direction, 'More than one face');
  });

  test('status events pass through (loading, errors)', () {
    expect(math.onEvent({'status': 'loading'}).status, 'loading');
    final e = math.onEvent({'status': 'error', 'error': 'boom'});
    expect(e.status, 'error');
    expect(e.error, 'boom');
  });

  test('the listening baseline becomes the new centre (median ignores short glances)', () {
    calibrate();
    math.baselineStart();
    for (var i = 0; i < 20; i++) {
      math.onEvent(frame(facePixels(noseShift: i < 18 ? 20 : -60))); // mostly head turned a little
      now += 66;
    }
    expect(math.baselineEnd(), 20);
    expect(math.onEvent(frame(facePixels(noseShift: 20))).direction, 'Looking at the screen');
  });

  test('a portrait phone picture and a landscape web picture of the same face give the same numbers', () {
    // Same face geometry (pixels) seen in a 640x480 web frame and in a 480x640 phone frame
    final px = facePixels(irisShift: 3, noseShift: 12, cx: 240);
    final web = <int, Pt>{for (final i in FaceMath.points) i: Pt(px[i]![0] / 640, px[i]![1] / 480)};
    final phone = <int, Pt>{
      for (final i in FaceMath.points) i: FaceMath.toTrackerSpace(px[i]![0] / 480, px[i]![1] / 640, 480, 640),
    };
    final a = FaceMath.raw(web), b = FaceMath.raw(phone);
    expect(b.h, closeTo(a.h, 1e-9));
    expect(b.v, closeTo(a.v, 1e-9));
    expect(b.open, closeTo(a.open, 1e-9));
    expect(b.yaw, closeTo(a.yaw, 1e-9));
    expect(b.pitch, closeTo(a.pitch, 1e-9));
  });
}
