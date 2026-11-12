import 'package:careerpilot/services/camera/face_sample.dart';
import 'package:careerpilot/services/camera/gaze_recorder.dart';
import 'package:careerpilot/services/turn_detector.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('answer ends after 3 s of quiet, only once the user has spoken', () {
    final d = TurnDetector();
    for (var i = 0; i < 40; i++) {
      expect(d.feed(0.01, 100), isNull); // 4 s of quiet before speaking: keep waiting
    }
    for (var i = 0; i < 20; i++) {
      expect(d.feed(0.3, 100), isNull); // 2 s of speech
    }
    String? r;
    for (var i = 0; i < 29; i++) {
      r = d.feed(0.01, 100);
    }
    expect(r, isNull); // 2.9 s quiet
    expect(d.feed(0.01, 100), 'end'); // 3.0 s quiet
    expect(d.feed(0.01, 100), isNull); // only once
  });

  test('a short pause in the middle does not end the answer', () {
    final d = TurnDetector();
    for (var i = 0; i < 10; i++) {
      d.feed(0.3, 100);
    }
    for (var i = 0; i < 20; i++) {
      expect(d.feed(0.01, 100), isNull); // 2 s thinking pause
    }
    d.feed(0.3, 100);
    expect(d.quietMs, 0);
  });

  test('a noisy room raises the speech threshold; a cough is not an answer', () {
    final d = TurnDetector();
    for (var i = 0; i < 100; i++) {
      d.feed(0.05, 100); // fan noise
    }
    expect(d.threshold, greaterThan(0.06));
    d.feed(0.5, 200); // cough
    expect(d.hasSpoken, isFalse);
  });

  test('no speech warning after 20 s', () {
    final d = TurnDetector();
    String? r;
    for (var i = 0; i < 200; i++) {
      r = d.feed(0.0, 100) ?? r;
    }
    expect(r, 'no_speech');
  });

  test('gaze letters', () {
    expect(GazeRecorder.codeFor(const FaceSample(status: 'ready')), 'N');
    expect(GazeRecorder.codeFor(const FaceSample(status: 'ready', face: true, faces: 1, eyesOpen: 0.3)), 'S');
    expect(GazeRecorder.codeFor(const FaceSample(status: 'ready', face: true, faces: 1, eyesOpen: 0.3, gazeV: 0.8)), 'd');
    expect(GazeRecorder.codeFor(const FaceSample(status: 'ready', face: true, faces: 1, eyesOpen: 0.3, headYaw: -0.6)), 'L');
    expect(GazeRecorder.codeFor(const FaceSample(status: 'ready', face: true, faces: 2, eyesOpen: 0.3)), 'M');
  });
}
