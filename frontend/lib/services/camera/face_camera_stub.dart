import 'package:flutter/material.dart';

import 'face_sample.dart';

class FaceCamera {
  static const supported = false;

  Future<String> start() async => 'unsupported';
  Future<String> track() async => 'unsupported';
  FaceSample latest() => FaceSample.off;
  void stop() {}
  void calibrate() {}
  void baselineStart() {}
  void baselineEnd() {}

  Widget preview() => const ColoredBox(
        color: Colors.black12,
        child: Center(child: Text('Camera check works in the web app for now.')),
      );
}
