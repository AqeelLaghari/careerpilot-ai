import 'dart:async';
import 'dart:io' show Platform;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'face_math.dart';
import 'face_sample.dart';

/// Camera + face tracking in the Android app (Day 29A): the front camera and Google's MediaPipe
/// Face Landmarker run on the phone (android/.../FaceTracker.kt); the gaze maths is the web app's,
/// in face_math.dart. Same interface as face_camera_web.dart, so the interview screens are shared.
/// The video never leaves the phone; only eye-contact letters are sent, as on the web.
class FaceCamera {
  static bool get supported => Platform.isAndroid;

  static const _methods = MethodChannel('careerpilot/face');
  static const _events = EventChannel('careerpilot/face/events');

  // One tracker for the whole app, like the web's window.cpCamera (calibration carries over).
  static final _math = FaceMath();
  static StreamSubscription<dynamic>? _sub;
  static FaceSample _sample = FaceSample.off;

  /// Ask for the camera and start it. "ok", NotAllowedError (permission denied), NotFoundError
  /// (no front camera), NotReadableError (in use), or "unsupported".
  Future<String> start() async {
    if (!supported) return 'unsupported';
    _sub ??= _events.receiveBroadcastStream().listen(
      (e) => _sample = _math.onEvent(Map<Object?, Object?>.from(e as Map)),
      onError: (Object e) => _sample = FaceSample(status: 'error', error: '$e'),
    );
    try {
      final r = await _methods.invokeMethod<String>('start') ?? 'error';
      if (r == 'ok' && _sample.status == 'off') _sample = const FaceSample(status: 'camera_on');
      return r;
    } on PlatformException catch (e) {
      return e.code;
    } on MissingPluginException {
      return 'unsupported';
    }
  }

  /// Load the face model (first time: a 3.6 MB download) and start tracking.
  Future<String> track() async {
    if (!supported) return 'unsupported';
    try {
      return await _methods.invokeMethod<String>('track') ?? 'error';
    } on PlatformException catch (e) {
      return e.code;
    } on MissingPluginException {
      return 'unsupported';
    }
  }

  FaceSample latest() => _sample;

  void stop() {
    _sample = FaceSample.off;
    if (!supported) return;
    _methods.invokeMethod<void>('stop').catchError((_) {});
  }

  void calibrate() => _math.recalibrate();
  void baselineStart() => _math.baselineStart();
  void baselineEnd() => _math.baselineEnd();

  /// The live camera picture (mirrored, like a selfie).
  Widget preview() => ClipRRect(
    borderRadius: BorderRadius.circular(12),
    child: const AndroidView(viewType: 'careerpilot/camera-preview'),
  );
}
