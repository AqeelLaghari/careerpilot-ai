import 'package:flutter/material.dart';

import '../../theme.dart';

/// Transcript of one spoken answer (fillers highlighted) + pace, fillers, pauses and tips.
class SpeechReport extends StatelessWidget {
  const SpeechReport({super.key, required this.transcript, required this.metrics, this.vision});
  final String transcript;
  final Map<String, dynamic> metrics;
  final Map<String, dynamic>? vision; // eye contact (null if the camera was off)

  static const _fillers = {'um', 'umm', 'uh', 'uhh', 'uhm', 'er', 'erm', 'ah', 'hmm', 'mm', 'eh'};
  static const _habits = {'basically', 'actually', 'literally', 'honestly', 'obviously', 'totally'};

  static Color _paceColor(String pace) => switch (pace) {
    'good' => AppColors.good,
    'a bit slow' || 'a bit fast' => AppColors.warn,
    _ => AppColors.bad,
  };

  /// Transcript with filler sounds and overused words marked in orange.
  Widget _transcript(BuildContext context) {
    final spans = <TextSpan>[];
    for (final word in transcript.split(' ')) {
      final w = word.toLowerCase().replaceAll(RegExp(r"[^a-z']"), '');
      final marked = _fillers.contains(w) || _habits.contains(w);
      spans.add(
        TextSpan(
          text: '$word ',
          style: marked
              ? TextStyle(color: AppColors.warn, fontWeight: FontWeight.bold, backgroundColor: Color(0x22F59E0B))
              : null,
        ),
      );
    }
    return SelectableText.rich(
      TextSpan(style: DefaultTextStyle.of(context).style.copyWith(height: 1.5), children: spans),
    );
  }

  List<Widget> _eyeContact() {
    final v = vision!;
    final pct = v['eye_contact_pct'] as num;
    final away = (v['away'] as List? ?? []).cast<Map>();
    final color = pct >= 70 ? AppColors.good : (pct >= 50 ? AppColors.warn : AppColors.bad);
    String at(num s) => '${s ~/ 60}:${(s % 60).round().toString().padLeft(2, '0')}';
    return [
      const SizedBox(height: 4),
      Row(
        children: [
          Icon(Icons.visibility_outlined, size: 18, color: color),
          const SizedBox(width: 6),
          Text(
            'Eye contact ${pct.round()}% · ${v['label']}',
            style: TextStyle(fontWeight: FontWeight.w600, color: color),
          ),
        ],
      ),
      for (final e in away.take(5))
        Padding(
          padding: const EdgeInsets.only(left: 24, top: 2),
          child: Text(
            '${at(e['at'] as num)}  looked ${e['where']} for ${(e['seconds'] as num).toStringAsFixed(0)} s',
            style: const TextStyle(fontSize: 12, color: Colors.grey),
          ),
        ),
      for (final t in (v['tips'] as List? ?? []).cast<String>().skip(pct >= 70 ? 1 : 0))
        Padding(
          padding: const EdgeInsets.only(top: 2),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.tips_and_updates_outlined, size: 16, color: AppColors.brand),
              const SizedBox(width: 6),
              Expanded(child: Text(t)),
            ],
          ),
        ),
      const SizedBox(height: 4),
    ];
  }

  Widget _stat(String value, String label, {Color? color}) => Padding(
    padding: const EdgeInsets.only(right: 20, bottom: 8),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          value,
          style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: color),
        ),
        Text(label, style: const TextStyle(fontSize: 12, color: Colors.grey)),
      ],
    ),
  );

  @override
  Widget build(BuildContext context) {
    final m = metrics;
    final fillers = (m['fillers'] as Map? ?? {}).cast<String, dynamic>();
    final habits = (m['habits'] as Map? ?? {}).cast<String, dynamic>();
    final tips = (m['tips'] as List? ?? []).cast<String>();
    final pace = (m['pace'] as String?) ?? '';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('What you said', style: TextStyle(fontWeight: FontWeight.w600)),
        const SizedBox(height: 4),
        if (transcript.trim().isEmpty)
          const Text('(no speech heard)', style: TextStyle(color: Colors.grey))
        else
          _transcript(context),
        const SizedBox(height: 12),
        Wrap(
          children: [
            _stat('${m['wpm']}', 'words / min · $pace', color: _paceColor(pace)),
            _stat(
              '${m['filler_count'] ?? 0}',
              'fillers (um, uh…)',
              color: (m['filler_count'] ?? 0) == 0 ? AppColors.good : null,
            ),
            _stat('${m['habit_count'] ?? 0}', 'overused phrases'),
            _stat('${m['long_pauses'] ?? 0}', 'long pauses (2 s+)'),
            _stat('${m['word_count'] ?? 0}', 'words'),
          ],
        ),
        if (fillers.isNotEmpty || habits.isNotEmpty)
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              for (final e in {...fillers, ...habits}.entries)
                Chip(
                  visualDensity: VisualDensity.compact,
                  label: Text('"${e.key}" × ${e.value}', style: const TextStyle(fontSize: 12)),
                ),
            ],
          ),
        if (vision != null && vision!['eye_contact_pct'] != null) ..._eyeContact(),
        if (tips.isNotEmpty) ...[
          const SizedBox(height: 8),
          for (final t in tips)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.tips_and_updates_outlined, size: 16, color: AppColors.brand),
                  const SizedBox(width: 6),
                  Expanded(child: Text(t)),
                ],
              ),
            ),
        ],
      ],
    );
  }
}
