import 'dart:async';

import 'package:flutter/material.dart';

import '../../services/api_client.dart';
import '../../theme.dart';
import 'speech_report.dart';

/// The report of a live interview (Day 21): overall score, the three parts, strengths and
/// improvements, and every answer graded with corrections and a stronger example.
/// Loads the session itself and waits while the server is still grading (about 20-40 s).
class InterviewReport extends StatefulWidget {
  const InterviewReport({super.key, required this.sessionId, this.onBack});
  final String sessionId;
  final VoidCallback? onBack;

  @override
  State<InterviewReport> createState() => _InterviewReportState();
}

class _InterviewReportState extends State<InterviewReport> {
  Map<String, dynamic>? _s;
  String? _error;
  Timer? _poll;
  int _tries = 0;

  static const _maxTries = 80; // x 3 s = 4 minutes

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Map<String, dynamic>? get _report => (_s?['report'] as Map?)?.cast<String, dynamic>();

  Future<void> _load() async {
    try {
      final s = await api.get('/interview/sessions/${widget.sessionId}');
      if (!mounted) return;
      setState(() {
        _s = s;
        _error = null;
      });
    } catch (e) {
      if (mounted) setState(() => _error = '$e'.replaceFirst('Exception: ', ''));
    }
    // still grading: ask again in a few seconds
    if (mounted && _report?['status'] != 'ready' && ++_tries < _maxTries) {
      _poll = Timer(const Duration(seconds: 3), _load);
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = _s;
    final back = widget.onBack == null
        ? null
        : FilledButton.icon(
            onPressed: widget.onBack,
            icon: const Icon(Icons.arrow_back),
            label: const Text('Back to Interview Coach'),
          );
    final r = _report;
    if (s == null || r == null || r['status'] != 'ready') {
      final failed = _tries >= _maxTries || (s == null && _error != null);
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (failed)
                Text(
                  _error ??
                      'The report is taking longer than usual. Open this interview again in a minute '
                          'from "Past interviews".',
                  textAlign: TextAlign.center,
                )
              else ...[
                CircularProgressIndicator(),
                SizedBox(height: 16),
                Text('Thank you! Grading your answers…', style: TextStyle(fontSize: 18)),
                SizedBox(height: 6),
                Text(
                  'Checking facts, key points and how you spoke. This takes about half a minute.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: AppColors.textMuted),
                ),
              ],
              if (back != null) ...[const SizedBox(height: 24), back],
            ],
          ),
        ),
      );
    }

    if (r['empty'] == true) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.mic_off, size: 48, color: AppColors.textMuted),
              const SizedBox(height: 12),
              Text('${r['summary']}', textAlign: TextAlign.center, style: const TextStyle(fontSize: 16)),
              if (back != null) ...[const SizedBox(height: 24), back],
            ],
          ),
        ),
      );
    }
    final grades = {
      for (final a in (r['answers'] as List? ?? []).cast<Map>()) a['turn_id'] as String: a.cast<String, dynamic>(),
    };
    final turns = (s['turns'] as List? ?? []).cast<Map<String, dynamic>>();
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 900),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _header(context, s, r, back),
                const SizedBox(height: 12),
                _summary(context, r),
                const SizedBox(height: 20),
                Text('Your answers', style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 4),
                Text(
                  'Each answer is scored out of 10. Personal facts (your projects, jobs, grades) are '
                  'not checked; technical facts are.',
                  style: TextStyle(color: AppColors.textMuted),
                ),
                const SizedBox(height: 8),
                for (final t in turns)
                  if (grades[t['id']] != null) _AnswerCard(turn: t, grade: grades[t['id']]!),
                if (back != null) ...[const SizedBox(height: 16), Center(child: back)],
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _header(BuildContext context, Map<String, dynamic> s, Map<String, dynamic> r, Widget? back) {
    final overall = (r['overall'] as num).round();
    final parts = (r['parts'] as Map).cast<String, dynamic>();
    final weights = (r['weights'] as Map? ?? {}).cast<String, dynamic>();
    final answered = (r['answers'] as List).length;
    String pct(String k) => weights[k] == null ? '' : ' · ${((weights[k] as num) * 100).round()}%';
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Wrap(
          spacing: 32,
          runSpacing: 20,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            SizedBox(
              width: 130,
              height: 130,
              child: Stack(
                alignment: Alignment.center,
                children: [
                  SizedBox.expand(
                    child: CircularProgressIndicator(
                      value: overall / 100,
                      strokeWidth: 12,
                      backgroundColor: AppColors.border,
                      color: AppColors.forScore(overall),
                    ),
                  ),
                  Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text('$overall', style: const TextStyle(fontSize: 38, fontWeight: FontWeight.bold)),
                      Text('${r['level']}', style: TextStyle(color: AppColors.forScore(overall))),
                    ],
                  ),
                ],
              ),
            ),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${s['role']} interview', style: Theme.of(context).textTheme.titleLarge),
                  Text(
                    '${s['minutes']} minutes · $answered answers graded',
                    style: TextStyle(color: AppColors.textMuted),
                  ),
                  const SizedBox(height: 12),
                  _bar('Content${pct('content')}', 'what you said', parts['content'] as num?),
                  _bar('Speaking${pct('speaking')}', 'pace, filler words, pauses', parts['speaking'] as num?),
                  _bar('Presence${pct('presence')}', 'eye contact', parts['presence'] as num?),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _bar(String label, String hint, num? value) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 5),
    child: Row(
      children: [
        SizedBox(
          width: 170,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: const TextStyle(fontWeight: FontWeight.w600)),
              Text(hint, style: TextStyle(color: AppColors.textMuted, fontSize: 11)),
            ],
          ),
        ),
        Expanded(
          child: value == null
              ? Text('no camera data', style: TextStyle(color: AppColors.textMuted))
              : ClipRRect(
                  borderRadius: BorderRadius.circular(6),
                  child: LinearProgressIndicator(
                    value: value / 100,
                    minHeight: 10,
                    backgroundColor: AppColors.border,
                    color: AppColors.forScore(value),
                  ),
                ),
        ),
        SizedBox(width: 44, child: Text(value == null ? '' : '${value.round()}', textAlign: TextAlign.right)),
      ],
    ),
  );

  Widget _summary(BuildContext context, Map<String, dynamic> r) {
    List<String> list(String k) => (r[k] as List? ?? []).map((e) => '$e').toList();
    Widget points(String title, IconData icon, Color color, List<String> items) => ConstrainedBox(
      constraints: const BoxConstraints(minWidth: 280, maxWidth: 420),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 6),
          for (final p in items)
            Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(icon, size: 18, color: color),
                  const SizedBox(width: 6),
                  Expanded(child: Text(p)),
                ],
              ),
            ),
        ],
      ),
    );
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${r['summary']}', style: const TextStyle(fontSize: 16, height: 1.4)),
            if (r['graded_by'] == 'rules')
              Padding(
                padding: EdgeInsets.only(top: 8),
                child: Text(
                  'The AI fact-checker was busy, so answers were scored by how well they matched the '
                  'key points. Open this report again later for a full check.',
                  style: TextStyle(color: AppColors.textMuted, fontSize: 12),
                ),
              ),
            const SizedBox(height: 16),
            Wrap(
              spacing: 32,
              runSpacing: 16,
              children: [
                points('What went well', Icons.check_circle, AppColors.good, list('strengths')),
                points('To improve', Icons.trending_up, AppColors.warn, list('improvements')),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// One question and the user's answer, with its grade.
class _AnswerCard extends StatelessWidget {
  const _AnswerCard({required this.turn, required this.grade});
  final Map<String, dynamic> turn;
  final Map<String, dynamic> grade;

  static final _verdicts = {
    'correct': ('Correct', AppColors.good),
    'partly_correct': ('Partly correct', AppColors.warn),
    'incorrect': ('Has mistakes', AppColors.bad),
  };

  @override
  Widget build(BuildContext context) {
    final score = (grade['score'] as num).round();
    final answer = (turn['answer'] as Map?)?.cast<String, dynamic>() ?? {};
    final transcript = (answer['transcript'] as String?) ?? '';
    final fixes = (grade['corrections'] as List? ?? []).cast<Map>();
    final covered = (grade['covered'] as List? ?? []).map((e) => '$e').toList();
    final missing = (grade['missing'] as List? ?? []).map((e) => '$e').toList();
    final verdict = _verdicts[grade['verdict']];
    final better = '${grade['better_answer'] ?? ''}';
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        turn['kind'] == 'follow_up' ? 'Follow-up question' : 'Interviewer',
                        style: TextStyle(color: AppColors.textMuted, fontSize: 12),
                      ),
                      Text('${turn['text']}', style: const TextStyle(fontWeight: FontWeight.w600)),
                    ],
                  ),
                ),
                const SizedBox(width: 12),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: AppColors.forScore(score * 10).withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    '$score/10',
                    style: TextStyle(fontWeight: FontWeight.bold, color: AppColors.forScore(score * 10)),
                  ),
                ),
              ],
            ),
            if (verdict != null)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text(
                  verdict.$1,
                  style: TextStyle(color: verdict.$2, fontWeight: FontWeight.w600, fontSize: 12),
                ),
              ),
            const SizedBox(height: 10),
            Text('Your answer', style: TextStyle(color: AppColors.textMuted, fontSize: 12)),
            SelectableText(
              transcript.isEmpty ? '(nothing was heard)' : transcript,
              style: const TextStyle(height: 1.4),
            ),
            for (final f in fixes)
              Container(
                width: double.infinity,
                margin: const EdgeInsets.only(top: 10),
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: AppColors.bad.withValues(alpha: 0.06),
                  borderRadius: BorderRadius.circular(10),
                  border: Border(left: BorderSide(color: AppColors.bad.withValues(alpha: 0.6), width: 3)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('You said: ${f['said']}', style: TextStyle(color: AppColors.bad)),
                    const SizedBox(height: 4),
                    Text('Correct: ${f['correct']}', style: const TextStyle(fontWeight: FontWeight.w600)),
                  ],
                ),
              ),
            if ('${grade['misheard'] ?? ''}'.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  'Possibly misheard by the speech recogniser: ${grade['misheard']} (not counted as a mistake)',
                  style: TextStyle(color: AppColors.textMuted, fontStyle: FontStyle.italic, fontSize: 12),
                ),
              ),
            if (covered.isNotEmpty || missing.isNotEmpty) ...[
              const SizedBox(height: 10),
              for (final c in covered) _point(Icons.check, AppColors.good, c),
              for (final m in missing) _point(Icons.add_circle_outline, AppColors.warn, 'Missing: $m'),
            ],
            if ('${grade['star'] ?? ''}'.isNotEmpty)
              _point(Icons.star_border, AppColors.warn, 'STAR: ${grade['star']}'),
            if ('${grade['feedback'] ?? ''}'.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 10),
                child: Text('${grade['feedback']}', style: const TextStyle(height: 1.4)),
              ),
            if (better.isNotEmpty)
              Theme(
                data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
                child: ExpansionTile(
                  tilePadding: EdgeInsets.zero,
                  title: Text('See a stronger answer', style: TextStyle(color: AppColors.brand)),
                  childrenPadding: const EdgeInsets.only(bottom: 8),
                  children: [
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: AppColors.good.withValues(alpha: 0.06),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Text(better, style: const TextStyle(height: 1.4, fontStyle: FontStyle.italic)),
                    ),
                  ],
                ),
              ),
            if (answer['metrics'] != null)
              Theme(
                data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
                child: ExpansionTile(
                  tilePadding: EdgeInsets.zero,
                  title: Text('How you spoke and eye contact', style: TextStyle(color: AppColors.brand)),
                  children: [
                    SpeechReport(
                      transcript: transcript,
                      metrics: (answer['metrics'] as Map).cast<String, dynamic>(),
                      vision: (answer['vision'] as Map?)?.cast<String, dynamic>(),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _point(IconData icon, Color color, String text) => Padding(
    padding: const EdgeInsets.only(top: 4),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 16, color: color),
        const SizedBox(width: 6),
        Expanded(child: Text(text, style: const TextStyle(fontSize: 13))),
      ],
    ),
  );
}
