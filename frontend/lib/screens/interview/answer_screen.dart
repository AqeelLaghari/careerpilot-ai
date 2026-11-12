import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:record/record.dart';

import '../../services/interview_socket.dart';
import '../../theme.dart';

/// Answer the interview questions out loud. The microphone audio is streamed to the
/// server while you speak; each answer is saved when you press Stop (or time runs out).
class AnswerScreen extends StatefulWidget {
  const AnswerScreen({super.key, required this.session});
  final Map<String, dynamic> session;

  @override
  State<AnswerScreen> createState() => _AnswerScreenState();
}

enum _Phase { connecting, idle, starting, recording, saving, error }

class _AnswerScreenState extends State<AnswerScreen> {
  late final List<Map<String, dynamic>> _questions =
      (widget.session['questions'] as List).cast<Map<String, dynamic>>();
  late final InterviewSocket _socket = InterviewSocket(widget.session['id'] as String);
  final _recorder = AudioRecorder();
  StreamSubscription<Map<String, dynamic>>? _sub;
  StreamSubscription<Uint8List>? _mic;
  Completer<void>? _micDone;
  Timer? _clock;

  _Phase _phase = _Phase.connecting;
  String? _message;
  int _index = 0;
  int _elapsed = 0; // seconds since recording started
  double _level = 0; // microphone loudness 0..1
  final Map<String, double> _saved = {}; // question id -> seconds recorded

  Map<String, dynamic> get _q => _questions[_index];
  int get _limit => (_q['time_limit_sec'] as num).toInt();

  @override
  void initState() {
    super.initState();
    _connect();
  }

  @override
  void dispose() {
    _clock?.cancel();
    _mic?.cancel();
    _recorder.dispose();
    _sub?.cancel();
    _socket.close();
    super.dispose();
  }

  Future<void> _connect() async {
    try {
      _sub = _socket.messages.listen(_onMessage);
      await _socket.connect();
    } catch (e) {
      _fail('Could not connect to the server. Is the backend running?');
    }
  }

  void _fail(String text) {
    if (mounted) {
      setState(() {
        _phase = _Phase.error;
        _message = text;
      });
    }
  }

  void _onMessage(Map<String, dynamic> m) {
    if (!mounted) return;
    switch (m['type']) {
      case 'ready':
        final answered = (m['answered'] as List).cast<String>().toSet();
        for (final id in answered) {
          _saved[id] = _saved[id] ?? 0;
        }
        final next = _questions.indexWhere((q) => !answered.contains(q['id']));
        setState(() {
          _phase = _Phase.idle;
          _index = next < 0 ? 0 : next;
        });
      case 'started':
        _startMic();
      case 'progress':
        break; // the local clock is smoother; the server confirms it is receiving audio
      case 'saved':
        setState(() {
          _saved[m['question_id'] as String] = (m['duration_sec'] as num).toDouble();
          _phase = _Phase.idle;
          _message = m['cut'] == true ? 'Time was up, so your answer was saved at the limit.' : null;
        });
      case 'error':
        if (m['code'] == 'auth' || m['code'] == 'session') {
          _fail(m['message'] as String);
        } else {
          _stopClockAndMic();
          setState(() {
            _phase = _Phase.idle;
            _message = m['message'] as String;
          });
        }
      case 'closed':
        if (_phase != _Phase.error) _fail('The connection to the server was closed. Go back and open the interview again.');
    }
  }

  Future<void> _record() async {
    if (!await _recorder.hasPermission()) {
      setState(() => _message = 'Microphone access is blocked. Allow the microphone for this site and try again.');
      return;
    }
    setState(() {
      _phase = _Phase.starting;
      _message = null;
      _elapsed = 0;
      _level = 0;
    });
    _socket.send({'type': 'start', 'question_id': _q['id']});
  }

  Future<void> _startMic() async {
    try {
      final stream = await _recorder.startStream(const RecordConfig(
        encoder: AudioEncoder.pcm16bits,
        sampleRate: 16000,
        numChannels: 1,
        echoCancel: true,
        noiseSuppress: true,
      ));
      _micDone = Completer<void>();
      _mic = stream.listen(
        (chunk) {
          _socket.sendAudio(chunk);
          final level = _loudness(chunk);
          if (mounted) setState(() => _level = level);
        },
        onDone: () => _micDone?.complete(),
      );
      setState(() => _phase = _Phase.recording);
      _clock = Timer.periodic(const Duration(seconds: 1), (_) {
        setState(() => _elapsed++);
        if (_elapsed >= _limit) _stop();
      });
    } catch (e) {
      _socket.send({'type': 'cancel'});
      setState(() {
        _phase = _Phase.idle;
        _message = 'Could not start the microphone: $e';
      });
    }
  }

  void _stopClockAndMic() {
    _clock?.cancel();
    _recorder.stop();
  }

  Future<void> _stop() async {
    if (_phase != _Phase.recording) return;
    setState(() => _phase = _Phase.saving);
    _clock?.cancel();
    await _recorder.stop();
    // Send "stop" only after the last audio chunk has gone out.
    await _micDone?.future.timeout(const Duration(seconds: 2), onTimeout: () {});
    await _mic?.cancel();
    _socket.send({'type': 'stop', 'question_id': _q['id']});
  }

  /// Root-mean-square loudness of 16-bit little-endian samples, scaled to 0..1.
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

  void _go(int i) {
    if (_phase == _Phase.idle) setState(() => _index = i);
  }

  String _mmss(int s) => '${s ~/ 60}:${(s % 60).toString().padLeft(2, '0')}';

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Interview · ${widget.session['role']}')),
      body: switch (_phase) {
        _Phase.connecting => const Center(child: CircularProgressIndicator()),
        _Phase.error => Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Text(_message ?? 'Something went wrong', textAlign: TextAlign.center),
            ),
          ),
        _ => _body(context),
      },
    );
  }

  Widget _body(BuildContext context) {
    final recording = _phase == _Phase.recording;
    final busy = _phase == _Phase.starting || _phase == _Phase.saving;
    final savedSecs = _saved[_q['id']];
    final left = _limit - _elapsed;
    return ListView(padding: const EdgeInsets.all(16), children: [
      Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 760),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            // Question picker: 1 2 3 ... (green = answered)
            Wrap(spacing: 6, runSpacing: 6, children: [
              for (var i = 0; i < _questions.length; i++)
                ChoiceChip(
                  label: Text('${i + 1}'),
                  selected: i == _index,
                  avatar: _saved.containsKey(_questions[i]['id'])
                      ? const Icon(Icons.check_circle, size: 16, color: AppColors.good)
                      : null,
                  onSelected: (recording || busy) ? null : (_) => _go(i),
                ),
            ]),
            const SizedBox(height: 16),
            Text('Question ${_index + 1} of ${_questions.length}', style: const TextStyle(color: Colors.grey)),
            const SizedBox(height: 6),
            Text(_q['question'] as String, style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 6),
            Text('You have about ${_mmss(_limit)} to answer.', style: const TextStyle(color: Colors.grey)),
            const SizedBox(height: 24),
            if (recording) ...[
              Row(children: [
                const Icon(Icons.fiber_manual_record, color: AppColors.bad, size: 18),
                const SizedBox(width: 6),
                Text('Recording ${_mmss(_elapsed)}', style: const TextStyle(fontWeight: FontWeight.w600)),
                const Spacer(),
                Text('${_mmss(left < 0 ? 0 : left)} left',
                    style: TextStyle(color: left <= 15 ? AppColors.bad : Colors.grey)),
              ]),
              const SizedBox(height: 8),
              // Live microphone level: if this bar doesn't move, the mic isn't hearing you.
              ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(value: _level, minHeight: 10, color: AppColors.good),
              ),
              const SizedBox(height: 4),
              const Text('Microphone level', style: TextStyle(fontSize: 12, color: Colors.grey)),
              const SizedBox(height: 16),
            ],
            if (savedSecs != null && !recording)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Row(children: [
                  const Icon(Icons.check_circle, color: AppColors.good),
                  const SizedBox(width: 6),
                  Text(savedSecs > 0
                      ? 'Answer saved (${savedSecs.toStringAsFixed(0)} s). You can record it again.'
                      : 'Answered earlier. You can record it again.'),
                ]),
              ),
            if (_message != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Text(_message!, style: const TextStyle(color: AppColors.warn)),
              ),
            Wrap(spacing: 12, runSpacing: 8, alignment: WrapAlignment.center, children: [
              if (!recording)
                FilledButton.icon(
                  onPressed: busy ? null : _record,
                  icon: busy
                      ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.mic),
                  label: Text(_phase == _Phase.saving
                      ? 'Saving…'
                      : savedSecs != null
                          ? 'Record again'
                          : 'Start answering'),
                )
              else
                FilledButton.icon(
                  style: FilledButton.styleFrom(backgroundColor: AppColors.bad),
                  onPressed: _stop,
                  icon: const Icon(Icons.stop),
                  label: const Text('Stop'),
                ),
              if (!recording && _index < _questions.length - 1)
                OutlinedButton.icon(
                  onPressed: busy ? null : () => _go(_index + 1),
                  icon: const Icon(Icons.arrow_forward),
                  label: const Text('Next question'),
                ),
              if (!recording && _saved.length == _questions.length)
                OutlinedButton.icon(
                  onPressed: () => Navigator.of(context).pop(true),
                  icon: const Icon(Icons.done_all),
                  label: const Text('Finish'),
                ),
            ]),
            const SizedBox(height: 24),
            Text('${_saved.length} of ${_questions.length} answered',
                textAlign: TextAlign.center, style: const TextStyle(color: Colors.grey)),
          ]),
        ),
      ),
    ]);
  }
}
