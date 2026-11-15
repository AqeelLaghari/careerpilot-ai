import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';

import 'profile_store.dart';

/// The interviewer's voice: the free text-to-speech built into the browser (web) or the
/// phone (Android). No internet service, no cost.
class Speaker {
  final _tts = FlutterTts();
  bool _ready = false;
  String? voiceName;

  Completer<void>? _done; // completes when the current sentence ends, is stopped or fails

  void _finished() {
    final d = _done;
    _done = null;
    if (d != null && !d.isCompleted) d.complete();
  }

  // Voice names that are clearly female / male (browser and phone voices don't say so directly)
  static const _female = [
    'female', 'zira', 'aria', 'jenny', 'samantha', 'susan', 'hazel', 'karen', 'moira', 'tessa', //
    'fiona', 'victoria', 'libby', 'sonia', 'emma', 'ava', 'michelle', 'heera', 'neerja', 'google us english',
  ];
  static const _male = [
    'male', 'david', 'mark', 'guy', 'george', 'ryan', 'daniel', 'alex', 'fred', 'christopher', //
    'eric', 'roger', 'steffan', 'thomas', 'andrew', 'brian', 'ravi', 'prabhat',
  ];

  static bool _isMale(String name) {
    final n = name.toLowerCase();
    if (n.contains('female')) return false;
    return _male.any(n.contains);
  }

  static bool _isFemale(String name) => _female.any(name.toLowerCase().contains) && !_isMale(name);

  /// Speed for the "speech rate" setting ("normal" is 1.0 in browsers but 0.5 on Android).
  static double rateFor(String speed) {
    final base = kIsWeb ? 0.95 : 0.5;
    return switch (speed) {
      'slow' => base * 0.82,
      'fast' => base * 1.18,
      _ => base,
    };
  }

  Future<void> _init() async {
    if (_ready) return;
    _ready = true;
    final wantMale = profileStore.setting('voice') == 'male';
    // We track the end ourselves: in Chrome a STOPPED sentence never reports "completed",
    // so waiting for speak() alone could hang forever (the End button bug).
    await _tts.awaitSpeakCompletion(false);
    _tts.setCompletionHandler(_finished);
    _tts.setCancelHandler(_finished);
    _tts.setErrorHandler((_) => _finished());
    await _tts.setLanguage('en-US');
    // "Normal" speed is 1.0 in browsers but 0.5 on Android
    await _tts.setSpeechRate(rateFor(profileStore.setting('speech_rate')));
    await _tts.setPitch(1.0);
    try {
      final voices = ((await _tts.getVoices) as List?)?.cast<Map>() ?? [];
      final english = voices.where((v) => '${v['locale']}'.toLowerCase().startsWith('en')).toList();
      // Clearer voices first: Windows/Edge "Natural" voices and Chrome's "Google" voices
      // The chosen voice type (Day 24 setting) comes first, then clarity
      int rank(Map v) {
        final n = '${v['name']}'.toLowerCase();
        final fits = wantMale ? _isMale(n) : _isFemale(n);
        final quality = n.contains('natural')
            ? 0
            : n.contains('google') && n.contains('us')
            ? 1
            : n.contains('google')
            ? 2
            : '${v['locale']}'.toLowerCase() == 'en-us'
            ? 3
            : 4;
        return (fits ? 0 : 10) + quality;
      }

      english.sort((a, b) => rank(a).compareTo(rank(b)));
      if (english.isNotEmpty) {
        final v = english.first;
        voiceName = '${v['name']}';
        await _tts.setVoice({'name': '${v['name']}', 'locale': '${v['locale']}'});
      }
    } catch (_) {
      // keep the default voice
    }
  }

  /// Say [text]; the Future completes when it has been spoken, stopped or failed, and at
  /// the latest after a safety limit based on its length (so nothing can wait forever).
  Future<void> say(String text) async {
    await _init();
    _finished(); // an earlier sentence still waiting: release it
    await _tts.stop();
    final done = _done = Completer<void>();
    final words = text.split(RegExp(r'\s+')).length;
    final limit = Duration(milliseconds: 4000 + words * 600); // ~100 words a minute + 4 s
    try {
      await _tts.speak(text);
    } catch (_) {
      _finished();
    }
    await done.future.timeout(limit, onTimeout: () {});
    if (identical(_done, done)) _done = null;
  }

  Future<void> stop() async {
    _finished();
    await _tts.stop();
  }
}
