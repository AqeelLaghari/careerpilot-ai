import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:record/record.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../../config.dart';
import '../../services/api_client.dart';
import '../../services/camera/face_camera.dart';
import '../../services/camera/gaze_recorder.dart';
import '../../services/profile_store.dart';
import '../../services/speaker.dart';
import '../../services/turn_detector.dart';
import '../../theme.dart';
import 'interview_report.dart';

/// The live video interview: your camera fills the screen like a video call, the
/// interviewer speaks (with subtitles), you answer naturally, and the next question comes
/// as soon as you finish. One continuous conversation of 5, 10 or 15 minutes.
class LiveInterviewScreen extends StatefulWidget {
  const LiveInterviewScreen({super.key, required this.minutes});
  final int minutes;

  @override
  State<LiveInterviewScreen> createState() => _LiveInterviewScreenState();
}

enum _Stage { preparing, lobby, connecting, interviewerSpeaking, listening, thinking, ended, failed }

class _LiveInterviewScreenState extends State<LiveInterviewScreen> {
  final _camera = FaceCamera();
  late final _gaze = GazeRecorder(_camera);
  Speaker _voice = Speaker(); // replaced by one for the interview's language
  final _recorder = AudioRecorder();
  final _turn = TurnDetector();

  WebSocketChannel? _ws;
  StreamSubscription<Uint8List>? _mic;
  Timer? _tick;
  Timer? _livePoll;

  _Stage _stage = _Stage.preparing;
  String? _sessionId;
  String _role = '';
  String _language = 'en'; // 'en' | 'ur' (Day 27)
  String _voiceMode = 'en'; // see Speaker.voiceLanguage
  String _subtitle = '';
  String? _turnId;
  String _kind = '';
  String? _error;
  int _remaining = 0; // seconds left in the interview
  double _level = 0;
  FaceSample _live = FaceSample.off;
  Future<void>? _speech; // the interviewer's current sentence
  bool _pauseSent = false; // told the server "the user went quiet" for this quiet spell
  bool _spokeSincePause = false;
  int _newSpeechMs = 0; // audio since the last piece the server was asked to transcribe
  bool _chunkSent = false; // a "chunk" was already sent in this quiet spell

  @override
  void initState() {
    super.initState();
    _remaining = widget.minutes * 60;
    _prepare();
  }

  @override
  void dispose() {
    _tick?.cancel();
    _livePoll?.cancel();
    _gaze.stop();
    _mic?.cancel();
    _recorder.dispose();
    _voice.stop();
    _camera.stop();
    _ws?.sink.close();
    super.dispose();
  }

  // ------------------------------------------------------------------ setup --
  /// Camera + microphone on, and the interview agenda made on the server, at the same time.
  Future<void> _prepare() async {
    final camera = _startCamera();
    try {
      // Find the voice first: for Urdu, the server then asks Gemini only for the script this
      // voice reads (+ Roman Urdu subtitles), which makes every next question quicker.
      _voice = Speaker(language: profileStore.setting('language'));
      _voiceMode = await _voice.ready();
      final s = await api.post('/interview/live', {
        'minutes': widget.minutes,
        'language': profileStore.setting('language'),
        'voice': _voiceMode,
      });
      _sessionId = s['id'] as String;
      _role = s['role'] as String;
      _language = (s['language'] as String?) ?? 'en';
      if (_language != _voice.language) {
        _voice = Speaker(language: _language);
        _voiceMode = await _voice.ready();
      }
    } catch (e) {
      _fail('$e'.replaceFirst('Exception: ', '').replaceFirst(RegExp(r'API error \d+: '), ''));
      return;
    }
    await camera;
    if (!await _recorder.hasPermission()) {
      _fail(
        kIsWeb
            ? 'Microphone access is blocked. Allow the microphone for this site and try again.'
            : 'Microphone access is blocked. Open Settings > Apps > CareerPilot AI > Permissions, allow the microphone, and try again.',
      );
      return;
    }
    if (mounted) setState(() => _stage = _Stage.lobby);
  }

  Future<void> _startCamera() async {
    if (!FaceCamera.supported) return;
    if (await _camera.start() != 'ok') return;
    _livePoll = Timer.periodic(const Duration(milliseconds: 300), (_) {
      if (mounted) setState(() => _live = _camera.latest());
    });
    await _camera.track();
  }

  void _fail(String text) {
    if (mounted) {
      setState(() {
        _stage = _Stage.failed;
        _error = text;
      });
    }
  }

  // -------------------------------------------------------------- interview --
  Future<void> _join() async {
    setState(() => _stage = _Stage.connecting);
    try {
      // One microphone stream for the whole interview; audio is only sent while answering.
      final stream = await _recorder.startStream(
        const RecordConfig(
          encoder: AudioEncoder.pcm16bits,
          sampleRate: 16000,
          numChannels: 1,
          echoCancel: true,
          noiseSuppress: true,
        ),
      );
      _mic = stream.listen(_onAudio);
      final ws = WebSocketChannel.connect(
        Uri.parse('${apiBaseUrl.replaceFirst(RegExp(r'^http'), 'ws')}/interview/live/ws'),
      );
      _ws = ws;
      await ws.ready;
      ws.stream.listen(
        (d) => _onMessage(jsonDecode(d as String) as Map<String, dynamic>),
        onDone: () {
          if (_stage != _Stage.ended && _stage != _Stage.failed) _fail('The connection to the server was lost.');
        },
      );
      final token = await FirebaseAuth.instance.currentUser?.getIdToken();
      _send({'type': 'auth', 'token': token ?? '', 'session_id': _sessionId});
      _tick = Timer.periodic(const Duration(seconds: 1), (_) {
        if (mounted && _remaining > 0 && _stage != _Stage.ended) setState(() => _remaining--);
      });
    } catch (e) {
      _fail('Could not start the interview: $e');
    }
  }

  void _send(Map<String, dynamic> m) => _ws?.sink.add(jsonEncode(m));

  Future<void> _onMessage(Map<String, dynamic> m) async {
    if (!mounted) return;
    switch (m['type']) {
      case 'say':
        _turnId = m['turn_id'] as String;
        _kind = m['kind'] as String;
        setState(() {
          _stage = _Stage.interviewerSpeaking;
          _subtitle = (m['roman'] as String?) ?? m['text'] as String; // Urdu: Roman Urdu subtitles
          _remaining = (m['remaining_sec'] as num).toInt().clamp(0, widget.minutes * 60);
        });
        _camera.baselineStart(); // listening = looking at the screen: re-measure "straight ahead"
        _speech = _voice.sayLine(m['text'] as String, hindi: m['hindi'] as String?);
        await _speech;
        _camera.baselineEnd();
        if (!mounted || _finishing || _stage != _Stage.interviewerSpeaking || _kind == 'goodbye') return;
        _turn.reset();
        _pauseSent = false;
        _spokeSincePause = false;
        _newSpeechMs = 0;
        _chunkSent = false;
        if (_camera.latest().status == 'ready') _gaze.start();
        _send({'type': 'listening', 'turn_id': _turnId});
        setState(() => _stage = _Stage.listening);
      case 'thinking':
        setState(() => _stage = _Stage.thinking);
      case 'ended':
        if (_finishing) return; // the user pressed End: already closed
        await _speech; // let the goodbye finish first (the voice always finishes, see Speaker)
        await _finish();
      case 'error':
        _fail(m['message'] as String);
    }
  }

  void _onAudio(Uint8List chunk) {
    final level = _loudness(chunk);
    if (_stage != _Stage.listening) {
      if (mounted && _level != 0) setState(() => _level = 0);
      return;
    }
    _ws?.sink.add(chunk);
    final event = _turn.feed(level, chunk.length ~/ 32); // 32 bytes per ms at 16 kHz
    if (mounted) setState(() => _level = level);
    _newSpeechMs += chunk.length ~/ 32;
    if (_turn.quietMs == 0) _chunkSent = false;
    // A short breath after 5+ s of speech: the server transcribes up to here while the user
    // carries on, so little is left to transcribe when the answer ends.
    if (_turn.hasSpoken && _turn.quietMs >= 400 && !_chunkSent && !_pauseSent && _newSpeechMs >= 5000) {
      _chunkSent = true;
      _newSpeechMs = 0;
      _send({'type': 'chunk'});
    }
    // Quiet for a moment after speaking: let the server start preparing the next question
    // now, so it is ready (almost) as soon as the answer ends.
    if (_turn.hasSpoken && _turn.quietMs >= 1200 && !_pauseSent) {
      _pauseSent = true;
      _spokeSincePause = false;
      _newSpeechMs = 0;
      _send({'type': 'pause'});
    } else if (_turn.quietMs == 0 && _pauseSent) {
      _pauseSent = false; // speaking again: the early guess will be ignored
      _spokeSincePause = true;
      _send({'type': 'resumed'}); // the server skips preparing that out-of-date question
    }
    if (event == 'end') _answered();
  }

  /// The user has finished: send where they looked, then hand the turn back.
  void _answered() {
    if (_stage != _Stage.listening) return;
    final codes = _gaze.stop();
    if (codes.isNotEmpty) _send({'type': 'vision', 'fps': _gaze.fps, 'codes': codes});
    _send({'type': 'answered', 'turn_id': _turnId, 'spoke_since_pause': _spokeSincePause || !_pauseSent});
    setState(() => _stage = _Stage.thinking);
  }

  Future<void> _endEarly() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('End the interview?'),
        content: const Text('Your answers so far will be kept for the report.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Continue')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('End')),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    _send({'type': 'end'});
    await _voice.stop();
    // Close everything now; don't wait for the server (its "ended" arrives later and is ignored).
    // The report screen waits until the server has saved and graded the interview.
    await _finish();
  }

  bool _finishing = false;

  /// Camera, microphone and voice off, then the report. Safe to call twice.
  Future<void> _finish() async {
    if (_finishing) return;
    _finishing = true;
    _tick?.cancel();
    _gaze.stop();
    await _voice.stop();
    await _mic?.cancel();
    _mic = null;
    try {
      await _recorder.stop();
    } catch (_) {}
    _camera.stop();
    _livePoll?.cancel();
    if (mounted) setState(() => _stage = _Stage.ended);
  }

  static double _loudness(Uint8List chunk) {
    final data = ByteData.sublistView(chunk);
    final n = chunk.length ~/ 2;
    if (n == 0) return 0;
    var sum = 0.0;
    for (var i = 0; i < n; i++) {
      final s = data.getInt16(i * 2, Endian.little) / 32768.0;
      sum += s * s;
    }
    return math.min(1, math.sqrt(sum / n) * 4);
  }

  String _mmss(int s) => '${s ~/ 60}:${(s % 60).toString().padLeft(2, '0')}';

  // --------------------------------------------------------------------- UI --
  @override
  Widget build(BuildContext context) {
    final inCall = {_Stage.interviewerSpeaking, _Stage.listening, _Stage.thinking, _Stage.connecting}.contains(_stage);
    return Scaffold(
      backgroundColor: inCall ? Colors.black : null,
      appBar: inCall ? null : AppBar(title: Text(_stage == _Stage.ended ? 'Interview report' : 'Live interview')),
      body: switch (_stage) {
        _Stage.preparing => _center(
          const Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              CircularProgressIndicator(),
              SizedBox(height: 16),
              Text('Preparing your interview from your CV…'),
            ],
          ),
        ),
        _Stage.lobby => _lobby(),
        _Stage.failed => _center(Text(_error ?? 'Something went wrong', textAlign: TextAlign.center)),
        _Stage.ended => _ended(),
        _ => _call(),
      },
    );
  }

  Widget _center(Widget child) => Center(
    child: Padding(padding: const EdgeInsets.all(24), child: child),
  );

  Widget _lobby() => ListView(
    padding: const EdgeInsets.all(16),
    children: [
      Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 640),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              AspectRatio(aspectRatio: 4 / 3, child: FaceCamera.supported ? _camera.preview() : const SizedBox()),
              const SizedBox(height: 8),
              Text(
                _live.status == 'ready' ? _live.direction : 'Starting camera…',
                textAlign: TextAlign.center,
                style: TextStyle(color: AppColors.textMuted),
              ),
              const SizedBox(height: 16),
              Text(
                '${widget.minutes}-minute interview · $_role',
                style: Theme.of(context).textTheme.titleLarge,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              const Text(
                'The interviewer will speak to you. Answer naturally, like a real interview. '
                'When you finish an answer, stay quiet for 3 seconds (or press "I\'m done") '
                'and the next question follows. Look at the camera while you speak. '
                'Keep each answer to about a minute, so there is time for more questions.',
                textAlign: TextAlign.center,
              ),
              if (_language == 'ur') ...[const SizedBox(height: 12), _urduNote()],
              const SizedBox(height: 20),
              FilledButton.icon(
                onPressed: _join,
                icon: const Icon(Icons.call),
                label: const Padding(padding: EdgeInsets.all(12), child: Text('Join interview')),
              ),
            ],
          ),
        ),
      ),
    ],
  );

  /// Urdu interview: what to expect, and a warning when this device has no voice to speak it.
  Widget _urduNote() {
    final (text, colour, icon) = switch (_voiceMode) {
      'ur' => (
        'Interview in Urdu. Answer in Urdu, or mix in English words as you normally would. '
            'Subtitles are in Roman Urdu, and your report will be in Roman Urdu.',
        AppColors.good,
        Icons.translate,
      ),
      'hi' => (
        'Interview in Urdu. Answer in Urdu, or mix in English words as you normally would. This browser has no '
            'Urdu voice, so a Hindi voice reads the questions (spoken, it sounds the same). Microsoft Edge or '
            'the Android app has a real Urdu voice.',
        AppColors.warn,
        Icons.record_voice_over_outlined,
      ),
      _ => (
        'This browser has no Urdu (or Hindi) voice, so the questions will appear as text only. '
            'Use Microsoft Edge or the Android app to hear them, or switch the interview language to '
            'English in Settings.',
        AppColors.bad,
        Icons.volume_off_outlined,
      ),
    };
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: colour.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(AppSizes.radius),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 20, color: colour),
          const SizedBox(width: 10),
          Expanded(
            child: Text(text, style: TextStyle(color: AppColors.text, height: 1.4)),
          ),
        ],
      ),
    );
  }

  /// Video-call layout: big camera, subtitles at the bottom, small status on top.
  Widget _call() {
    final listening = _stage == _Stage.listening;
    final countdown = listening ? _turn.countdown : null;
    final status = switch (_stage) {
      _Stage.connecting => 'Connecting…',
      _Stage.interviewerSpeaking => 'Interviewer speaking',
      _Stage.listening => countdown != null ? 'Finishing in $countdown…' : 'Listening',
      _ => 'Interviewer is thinking…',
    };
    return SafeArea(
      child: Stack(
        children: [
          Positioned.fill(child: FaceCamera.supported ? _camera.preview() : const ColoredBox(color: Colors.black)),
          // top bar: interviewer status, time left, end
          Positioned(
            left: 12,
            right: 12,
            top: 12,
            child: Row(
              children: [
                _pill(
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        _stage == _Stage.interviewerSpeaking
                            ? Icons.graphic_eq
                            : listening
                            ? Icons.mic
                            : Icons.more_horiz,
                        size: 18,
                        color: listening ? AppColors.good : Colors.white,
                      ),
                      const SizedBox(width: 6),
                      Text(status, style: const TextStyle(color: Colors.white)),
                    ],
                  ),
                ),
                const Spacer(),
                _pill(
                  Text(
                    _mmss(_remaining),
                    style: const TextStyle(color: Colors.white, fontFeatures: []),
                  ),
                ),
                const SizedBox(width: 8),
                FilledButton.icon(
                  style: FilledButton.styleFrom(backgroundColor: AppColors.bad),
                  onPressed: _endEarly,
                  icon: const Icon(Icons.call_end, size: 18),
                  label: const Text('End'),
                ),
              ],
            ),
          ),
          // eye-contact light
          if (_live.status == 'ready')
            Positioned(
              left: 12,
              top: 60,
              child: _pill(
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.circle, size: 10, color: _live.lookingAtScreen ? AppColors.good : AppColors.warn),
                    const SizedBox(width: 6),
                    Text(
                      _live.lookingAtScreen ? 'Good eye contact' : _live.direction,
                      style: const TextStyle(color: Colors.white, fontSize: 12),
                    ),
                  ],
                ),
              ),
            ),
          // subtitles + answer controls
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: Container(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 20),
              decoration: const BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [Colors.transparent, Color(0xCC000000)],
                ),
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (_subtitle.isNotEmpty)
                    ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 900),
                      child: Text(
                        _subtitle,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          color: Colors.white.withValues(alpha: _stage == _Stage.interviewerSpeaking ? 1 : 0.7),
                          fontSize: 20,
                          height: 1.35,
                          shadows: const [Shadow(blurRadius: 4)],
                        ),
                      ),
                    ),
                  const SizedBox(height: 14),
                  if (listening)
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        SizedBox(
                          width: 160,
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(4),
                            child: LinearProgressIndicator(
                              value: _level,
                              minHeight: 6,
                              color: AppColors.good,
                              backgroundColor: Colors.white24,
                            ),
                          ),
                        ),
                        const SizedBox(width: 16),
                        FilledButton.icon(
                          onPressed: _answered,
                          icon: const Icon(Icons.check),
                          label: const Text("I'm done"),
                        ),
                      ],
                    )
                  else if (_stage == _Stage.thinking)
                    const SizedBox(
                      width: 120,
                      child: LinearProgressIndicator(
                        minHeight: 3,
                        color: Colors.white,
                        backgroundColor: Colors.white24,
                      ),
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _pill(Widget child) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
    decoration: BoxDecoration(color: const Color(0x99000000), borderRadius: BorderRadius.circular(20)),
    child: child,
  );

  /// After the interview: the graded report (it waits while the server grades).
  Widget _ended() => _sessionId == null
      ? _center(const Text('The interview has ended.'))
      : InterviewReport(sessionId: _sessionId!, onBack: () => Navigator.of(context).pop());
}
