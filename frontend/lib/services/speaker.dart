import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';

import 'profile_store.dart';

/// The interviewer's voice: the free text-to-speech built into the browser (web) or the
/// phone (Android). No internet service, no cost.
///
/// Urdu interviews (Day 27): an Urdu voice reads the Urdu script (Microsoft Edge and Android
/// have one). Chrome on a computer has none, so a Hindi voice reads the same sentence written
/// in Devanagari: spoken Urdu and Hindi sound the same. With neither, nothing is spoken and
/// the subtitles stay on screen long enough to read.
class Speaker {
  Speaker({String? language}) : language = language ?? profileStore.setting('language');

  /// The interview language: 'en' or 'ur'.
  final String language;

  final _tts = FlutterTts();
  Future<void>? _ready;
  String? voiceName;

  /// The voice actually used: 'en', 'ur', 'hi' (Urdu read by a Hindi voice) or 'none'.
  String voiceLanguage = 'en';

  Completer<void>? _done; // completes when the current sentence ends, is stopped or fails

  void _finished() {
    final d = _done;
    _done = null;
    if (d != null && !d.isCompleted) d.complete();
  }

  // Voice names that are clearly female / male (browser and phone voices don't say so directly)
  static const _female = [
    'female', 'zira', 'aria', 'jenny', 'samantha', 'susan', 'hazel', 'karen', 'moira', 'tessa', //
    'fiona', 'victoria', 'libby', 'sonia', 'emma', 'ava', 'michelle', 'heera', 'neerja', 'google us english', //
    'uzma', 'gul', 'swara', 'kalpana', 'google हिन्दी', 'lekha',
  ];
  static const _male = [
    'male', 'david', 'mark', 'guy', 'george', 'ryan', 'daniel', 'alex', 'fred', 'christopher', //
    'eric', 'roger', 'steffan', 'thomas', 'andrew', 'brian', 'ravi', 'prabhat', 'asad', 'salman', 'madhur', //
    'hemant',
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

  /// The best voice for [prefix] ('en', 'ur', 'hi'): the chosen voice type (female/male) first,
  /// then clarity (Edge "Natural" voices, then Chrome's "Google" voices).
  static Map? bestVoice(List<Map> voices, String prefix, {required bool wantMale}) {
    final fit = voices.where((v) => '${v['locale']}'.toLowerCase().startsWith(prefix)).toList();
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

    fit.sort((a, b) => rank(a).compareTo(rank(b)));
    return fit.isEmpty ? null : fit.first;
  }

  /// Picks the voice once; returns [voiceLanguage].
  Future<String> ready() async {
    await (_ready ??= _init());
    return voiceLanguage;
  }

  Future<void> _init() async {
    final wantMale = profileStore.setting('voice') == 'male';
    // We track the end ourselves: in Chrome a STOPPED sentence never reports "completed",
    // so waiting for speak() alone could hang forever (the End button bug).
    await _tts.awaitSpeakCompletion(false);
    _tts.setCompletionHandler(_finished);
    _tts.setCancelHandler(_finished);
    _tts.setErrorHandler((_) => _finished());
    await _tts.setSpeechRate(rateFor(profileStore.setting('speech_rate')));
    await _tts.setPitch(1.0);
    var voices = <Map>[];
    try {
      voices = ((await _tts.getVoices) as List?)?.cast<Map>() ?? [];
    } catch (_) {
      // keep the default voice
    }
    final order = language == 'ur' ? ['ur', 'hi'] : ['en'];
    for (final prefix in order) {
      final v = bestVoice(voices, prefix, wantMale: wantMale);
      if (v == null) continue;
      voiceLanguage = prefix;
      voiceName = '${v['name']}';
      try {
        await _tts.setLanguage('${v['locale']}');
        await _tts.setVoice({'name': '${v['name']}', 'locale': '${v['locale']}'});
      } catch (_) {}
      return;
    }
    if (language == 'ur') {
      voiceLanguage = 'none'; // no Urdu or Hindi voice: subtitles only
    } else {
      await _tts.setLanguage('en-US'); // no voice list (some browsers): the default English voice
    }
  }

  /// Say one interviewer line. Urdu lines come as [text] (Urdu script) + [hindi] (the same
  /// sentence in Devanagari, read by a Hindi voice when there is no Urdu one).
  Future<void> sayLine(String text, {String? hindi}) async {
    final mode = await ready();
    return say(mode == 'hi' && hindi != null && hindi.isNotEmpty ? hindi : text);
  }

  /// Say [text]; the Future completes when it has been spoken, stopped or failed, and at
  /// the latest after a safety limit based on its length (so nothing can wait forever).
  Future<void> say(String text) async {
    await ready();
    _finished(); // an earlier sentence still waiting: release it
    await _tts.stop();
    final done = _done = Completer<void>();
    final words = text.split(RegExp(r'\s+')).length;
    if (voiceLanguage == 'none') {
      // nothing can speak it: leave time to read the subtitles (~200 words a minute + 2 s)
      await Future.any([done.future, Future<void>.delayed(Duration(milliseconds: 2000 + words * 300))]);
      if (identical(_done, done)) _done = null;
      return;
    }
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
