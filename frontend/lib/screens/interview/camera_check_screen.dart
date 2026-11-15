import 'dart:async';

import 'package:flutter/material.dart';

import '../../services/camera/face_camera.dart';
import '../../theme.dart';

/// Check the camera and face tracking before an interview: live picture, "face found",
/// where the eyes and head point. The video stays in the browser; nothing is uploaded.
class CameraCheckScreen extends StatefulWidget {
  const CameraCheckScreen({super.key});

  @override
  State<CameraCheckScreen> createState() => _CameraCheckScreenState();
}

class _CameraCheckScreenState extends State<CameraCheckScreen> {
  final _camera = FaceCamera();
  Timer? _poll;
  FaceSample _s = FaceSample.off;
  String? _problem;
  bool _started = false;

  @override
  void initState() {
    super.initState();
    _start();
  }

  @override
  void dispose() {
    _poll?.cancel();
    _camera.stop();
    super.dispose();
  }

  Future<void> _start() async {
    final r = await _camera.start();
    if (!mounted) return;
    if (r != 'ok') {
      setState(
        () => _problem = switch (r) {
          'NotAllowedError' =>
            'Camera access is blocked. Click the camera icon in the address bar, allow it, and reload.',
          'NotFoundError' => 'No camera was found. Connect a webcam and try again.',
          'NotReadableError' => 'The camera is being used by another app (Zoom, Teams…). Close it and try again.',
          'unsupported' => 'Camera check works in the web app for now.',
          _ => 'The camera could not start ($r).',
        },
      );
      return;
    }
    setState(() => _started = true);
    _poll = Timer.periodic(const Duration(milliseconds: 200), (_) {
      if (mounted) setState(() => _s = _camera.latest());
    });
    final t = await _camera.track();
    if (t != 'ok' && mounted) setState(() => _problem = 'Face tracking could not start ($t). The camera still works.');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Camera check')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 560),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text(
                    'Sit so your face is in the middle, with light in front of you. '
                    'The video stays on your computer; only eye-contact numbers are used.',
                    style: TextStyle(color: Colors.grey),
                  ),
                  const SizedBox(height: 12),
                  AspectRatio(
                    aspectRatio: 4 / 3,
                    child: _problem != null && !_started
                        ? Container(
                            decoration: BoxDecoration(color: Colors.black12, borderRadius: BorderRadius.circular(12)),
                            padding: const EdgeInsets.all(24),
                            alignment: Alignment.center,
                            child: Text(_problem!, textAlign: TextAlign.center),
                          )
                        : _camera.preview(),
                  ),
                  const SizedBox(height: 12),
                  if (_problem != null && _started) Text(_problem!, style: const TextStyle(color: AppColors.warn)),
                  if (_started) _status(),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _status() {
    final s = _s;
    if (s.status == 'loading' || s.status == 'camera_on') {
      return const Row(
        children: [
          SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
          SizedBox(width: 8),
          Text('Loading face tracking… (first time takes a few seconds)'),
        ],
      );
    }
    if (s.status == 'camera_ended') {
      return const Text('The camera stopped. Check that it is connected.', style: TextStyle(color: AppColors.bad));
    }
    if (s.status == 'error') {
      return Text('Face tracking error: ${s.error}', style: const TextStyle(color: AppColors.bad));
    }
    final good = s.lookingAtScreen;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(good ? Icons.check_circle : Icons.info_outline, color: good ? AppColors.good : AppColors.warn),
            const SizedBox(width: 8),
            Text(
              s.direction,
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w600,
                color: good ? AppColors.good : AppColors.warn,
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        if (s.face) ...[
          _bar('Eyes left ↔ right', s.gazeH),
          _bar('Eyes up ↕ down', s.gazeV),
          _bar('Head left ↔ right', s.headYaw),
          _bar('Head up ↕ down', s.headPitch),
          const SizedBox(height: 6),
          Text(
            'Eye opening ${s.eyesOpen.toStringAsFixed(2)} · ${s.fps} checks per second',
            style: const TextStyle(color: Colors.grey, fontSize: 12),
          ),
        ],
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              child: Text(
                s.calibrated
                    ? 'Centre = your normal position. If the dots are off-centre while you look at the screen, recalibrate.'
                    : 'Look at the middle of the screen for a moment to set your centre.',
                style: const TextStyle(color: Colors.grey, fontSize: 12),
              ),
            ),
            TextButton.icon(
              onPressed: _camera.calibrate,
              icon: const Icon(Icons.center_focus_strong, size: 18),
              label: const Text('Recalibrate'),
            ),
          ],
        ),
      ],
    );
  }

  /// A value from -1 to +1 shown as a marker on a bar (centre = straight ahead).
  Widget _bar(String label, double v) {
    final x = v.clamp(-1.0, 1.0);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          SizedBox(width: 140, child: Text(label, style: const TextStyle(fontSize: 13))),
          Expanded(
            child: LayoutBuilder(
              builder: (_, c) => SizedBox(
                height: 14,
                child: Stack(
                  children: [
                    Positioned.fill(
                      child: DecoratedBox(
                        decoration: BoxDecoration(color: Colors.black12, borderRadius: BorderRadius.circular(7)),
                      ),
                    ),
                    Positioned(
                      left: c.maxWidth / 2 - 1,
                      top: 0,
                      bottom: 0,
                      child: Container(width: 2, color: Colors.black26),
                    ),
                    Positioned(
                      left: (x + 1) / 2 * (c.maxWidth - 14),
                      top: 0,
                      child: Container(
                        width: 14,
                        height: 14,
                        decoration: BoxDecoration(
                          color: x.abs() < 0.35 ? AppColors.good : AppColors.warn,
                          shape: BoxShape.circle,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          SizedBox(
            width: 48,
            child: Text(v.toStringAsFixed(2), textAlign: TextAlign.right, style: const TextStyle(fontSize: 12)),
          ),
        ],
      ),
    );
  }
}
