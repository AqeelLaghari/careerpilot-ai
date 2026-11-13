/// Decides when the user has finished answering, from the microphone loudness:
/// they have spoken, and then stayed quiet for [silenceMs].
///
/// Background noise = the quietest moment in the last [windowMs] (there are always tiny gaps
/// between words, so this finds the room's level even while the user talks). A fan or a
/// noisy room therefore doesn't count as speech: speech = louder than
/// max(minLevel, noise x noiseFactor). minLevel is low on purpose so a soft voice counts.
class TurnDetector {
  TurnDetector({
    this.silenceMs = 5000,
    this.minSpeechMs = 600,
    this.noSpeechMs = 20000,
    this.minLevel = 0.035,
    this.noiseFactor = 2.0,
    this.windowMs = 4000,
  });

  final int silenceMs; // quiet this long after speaking = end of the answer
  final int minSpeechMs; // this much speech before an answer can end (ignores a cough)
  final int noSpeechMs; // nothing said this long = "we can't hear you"
  final double minLevel;
  final double noiseFactor;
  final int windowMs;
  final List<(double, int)> _recent = []; // (level, ms) of the last windowMs

  double noise = 0.01;
  int spokenMs = 0;
  int quietMs = 0;
  int elapsedMs = 0;
  bool _ended = false;
  bool _warned = false;

  bool get hasSpoken => spokenMs >= minSpeechMs;
  double get threshold => noise * noiseFactor > minLevel ? noise * noiseFactor : minLevel;

  /// Seconds left before the answer ends by itself, once the user has been quiet for a
  /// while (null = not counting down). Used for "Finishing in 3…".
  int? get countdown {
    if (!hasSpoken || _ended || quietMs < 2000) return null;
    final left = silenceMs - quietMs;
    return left <= 0 ? 0 : (left + 999) ~/ 1000;
  }

  /// Feed one chunk: [level] 0..1 and its length in ms.
  /// Returns 'end' (answer finished), 'no_speech' (once), or null.
  String? feed(double level, int ms) {
    if (_ended) return null;
    elapsedMs += ms;
    _recent.add((level, ms));
    var total = _recent.fold<int>(0, (t, e) => t + e.$2);
    while (total - _recent.first.$2 >= windowMs) {
      total -= _recent.removeAt(0).$2;
    }
    noise = _recent.map((e) => e.$1).reduce((a, b) => a < b ? a : b);
    if (level >= threshold) {
      spokenMs += ms;
      quietMs = 0;
    } else {
      quietMs += ms;
    }
    if (hasSpoken && quietMs >= silenceMs) {
      _ended = true;
      return 'end';
    }
    if (!hasSpoken && !_warned && elapsedMs >= noSpeechMs) {
      _warned = true;
      return 'no_speech';
    }
    return null;
  }

  void reset() {
    spokenMs = 0;
    quietMs = 0;
    elapsedMs = 0;
    _ended = false;
    _warned = false;
  }
}
