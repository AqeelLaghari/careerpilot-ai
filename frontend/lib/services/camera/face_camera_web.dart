import 'dart:convert';
import 'dart:js_interop';
import 'dart:ui_web' as ui_web;

import 'package:flutter/widgets.dart';
import 'package:web/web.dart' as web;

import 'face_sample.dart';

@JS('cpCamera')
external _CpCamera? get _cp;

/// The JavaScript object from web/face_tracker.js
extension type _CpCamera._(JSObject _) implements JSObject {
  external JSPromise<JSString> start();
  external JSPromise<JSString> track();
  external web.HTMLElement container();
  external JSString latest();
  external void stop();
  external void calibrate();
  external void baselineStart();
  external JSNumber baselineEnd();
}

class FaceCamera {
  static const supported = true;
  static const _viewType = 'cp-camera-view';
  static bool _registered = false;

  /// Ask for the camera and show it. Returns "ok" or the browser's error name
  /// (NotAllowedError = permission denied, NotFoundError = no camera).
  Future<String> start() async {
    final cp = _cp;
    if (cp == null) return 'script_missing';
    return (await cp.start().toDart).toDart;
  }

  /// Load MediaPipe (first time: about 4 MB) and start tracking the face.
  Future<String> track() async {
    final cp = _cp;
    if (cp == null) return 'script_missing';
    return (await cp.track().toDart).toDart;
  }

  FaceSample latest() {
    final cp = _cp;
    if (cp == null) return FaceSample.off;
    return FaceSample.fromJson(jsonDecode(cp.latest().toDart) as Map<String, dynamic>);
  }

  void stop() => _cp?.stop();

  /// The next 1.5 s of looking at the screen become the new "straight ahead".
  void calibrate() => _cp?.calibrate();

  /// Live interview: while the interviewer speaks, the user looks at the screen; the middle
  /// of that time becomes "straight ahead" for the next answer (see face_tracker.js).
  void baselineStart() => _cp?.baselineStart();
  void baselineEnd() => _cp?.baselineEnd();

  /// The live camera picture. Each view gets its own <video> showing the same camera
  /// stream (moving one video between screens freezes it in Chrome).
  Widget preview() {
    if (!_registered) {
      ui_web.platformViewRegistry.registerViewFactory(_viewType, (int id) => _cp!.container());
      _registered = true;
    }
    return const HtmlElementView(viewType: _viewType);
  }
}
