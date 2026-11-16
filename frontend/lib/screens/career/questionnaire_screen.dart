import 'package:flutter/material.dart';

import '../../services/api_client.dart';
import '../../theme.dart';

/// Adaptive questionnaire: one question at a time.
/// The BACKEND decides what to ask (only what the resume is missing), so after
/// every answer we send it and show whatever question the backend says is next.
/// Returns true to the previous screen if anything was answered.
class QuestionnaireScreen extends StatefulWidget {
  const QuestionnaireScreen({super.key});

  @override
  State<QuestionnaireScreen> createState() => _QuestionnaireScreenState();
}

class _QuestionnaireScreenState extends State<QuestionnaireScreen> {
  List<Map<String, dynamic>> _questions = [];
  int _answered = 0;
  bool _loading = true;
  bool _sending = false;
  bool _changed = false;
  String? _error;
  final Set<String> _skipped = {};

  // the current answer being edited
  String? _single;
  final Set<String> _multi = {};
  final Map<String, String> _rating = {};
  final _textCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _textCtrl.dispose();
    super.dispose();
  }

  void _apply(Map<String, dynamic> r) {
    _questions = (r['questions'] as List).cast<Map<String, dynamic>>();
    _answered = (r['progress'] as Map)['answered'] as int;
    _resetInput();
  }

  Future<void> _load() async {
    try {
      final r = await api.get('/questionnaire');
      if (mounted) setState(() => _apply(r));
    } catch (e) {
      if (mounted) setState(() => _error = _clean(e));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _resetInput() {
    _single = null;
    _multi.clear();
    _rating.clear();
    _textCtrl.clear();
    _error = null;
  }

  Map<String, dynamic>? get _current {
    for (final q in _questions) {
      if (!_skipped.contains(q['id'])) return q;
    }
    return null;
  }

  String _clean(Object e) => '$e'.replaceFirst('Exception: ', '').replaceFirst(RegExp(r'API error \d+: '), '');

  /// The answer in the shape the backend expects for this question type.
  Object? _value(Map<String, dynamic> q) {
    final other = _textCtrl.text.trim();
    switch (q['type']) {
      case 'single':
        return _single;
      case 'role':
        return other.isNotEmpty ? other : _single;
      case 'multi':
        final typed = other.isEmpty ? <String>[] : other.split(',').map((s) => s.trim()).where((s) => s.isNotEmpty);
        return [..._multi, ...typed];
      case 'number':
        return num.tryParse(other);
      case 'text':
        return other.isEmpty ? null : other;
      case 'rating':
        return Map<String, String>.from(_rating);
    }
    return null;
  }

  bool _ready(Map<String, dynamic> q) {
    final v = _value(q);
    if (v == null) return false;
    if (q['type'] == 'rating') return _rating.length == (q['items'] as List).length;
    return true; // an empty multi-select is a valid answer ("none of these")
  }

  Future<void> _submit(Map<String, dynamic> q) async {
    setState(() => _sending = true);
    try {
      final r = await api.post('/questionnaire/answers', {
        'answers': {q['id']: _value(q)},
      });
      final err = (r['errors'] as Map)[q['id']];
      if (err != null) {
        setState(() => _error = '$err');
      } else {
        _changed = true;
        setState(() => _apply(r));
      }
    } catch (e) {
      setState(() => _error = _clean(e));
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final q = _current;
    final total = _answered + _questions.length;
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) Navigator.pop(context, _changed);
      },
      child: Scaffold(
        appBar: AppBar(title: const Text('A few quick questions')),
        body: _loading
            ? const Center(child: CircularProgressIndicator())
            : Column(
                children: [
                  LinearProgressIndicator(
                    value: total == 0 ? 1 : _answered / total,
                    minHeight: 6,
                    color: AppColors.good,
                    backgroundColor: AppColors.border,
                  ),
                  Expanded(
                    child: Center(
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 640),
                        child: q == null ? _done() : _question(q, total),
                      ),
                    ),
                  ),
                ],
              ),
      ),
    );
  }

  Widget _done() => Padding(
    padding: const EdgeInsets.all(24),
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(Icons.check_circle, size: 72, color: AppColors.good),
        const SizedBox(height: 12),
        Text(_questions.isEmpty ? 'All done!' : 'That\'s it for now', style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: 8),
        Text(
          _questions.isEmpty
              ? 'Your career matches and roadmap now use your answers.'
              : 'You skipped ${_skipped.length} question(s). You can answer them later from the Career tab.',
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 20),
        FilledButton(onPressed: () => Navigator.pop(context, _changed), child: const Text('Back to Career')),
      ],
    ),
  );

  Widget _question(Map<String, dynamic> q, int total) {
    final t = Theme.of(context).textTheme;
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Text('Question ${_answered + 1} of $total', style: TextStyle(color: AppColors.textMuted)),
        const SizedBox(height: 8),
        Text(q['text'] as String, style: t.headlineSmall),
        if (q['why'] != null) ...[
          const SizedBox(height: 8),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.info_outline, size: 18, color: AppColors.textMuted),
              const SizedBox(width: 6),
              Expanded(
                child: Text(q['why'] as String, style: TextStyle(color: AppColors.textMuted)),
              ),
            ],
          ),
        ],
        const SizedBox(height: 20),
        _input(q),
        if (_error != null) ...[const SizedBox(height: 12), Text(_error!, style: TextStyle(color: AppColors.bad))],
        const SizedBox(height: 24),
        Row(
          children: [
            TextButton(
              onPressed: _sending
                  ? null
                  : () => setState(() {
                      _skipped.add(q['id'] as String);
                      _resetInput();
                    }),
              child: const Text('Skip'),
            ),
            const Spacer(),
            FilledButton.icon(
              onPressed: _sending || !_ready(q) ? null : () => _submit(q),
              icon: _sending
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.arrow_forward),
              label: const Text('Next'),
            ),
          ],
        ),
      ],
    );
  }

  // One input widget per question type
  Widget _input(Map<String, dynamic> q) {
    final options = ((q['options'] as List?) ?? []).cast<Map<String, dynamic>>();
    switch (q['type']) {
      case 'single':
      case 'role':
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            RadioGroup<String>(
              groupValue: _single,
              onChanged: (v) => setState(() {
                _single = v;
                _textCtrl.clear();
              }),
              child: Column(
                children: [
                  for (final o in options)
                    RadioListTile<String>(
                      value: o['value'] as String,
                      title: Text(o['label'] as String),
                      contentPadding: EdgeInsets.zero,
                    ),
                ],
              ),
            ),
            if (q['allow_other'] == true)
              TextField(
                controller: _textCtrl,
                decoration: const InputDecoration(labelText: 'Or type another role', border: OutlineInputBorder()),
                onChanged: (_) => setState(() => _single = null),
              ),
          ],
        );
      case 'multi':
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final o in options)
                  FilterChip(
                    label: Text(o['label'] as String),
                    selected: _multi.contains(o['value']),
                    onSelected: (on) => setState(() {
                      final v = o['value'] as String;
                      if (on) {
                        final max = q['max_choices'] as int?;
                        if (max == null || _multi.length < max) _multi.add(v);
                      } else {
                        _multi.remove(v);
                      }
                    }),
                  ),
              ],
            ),
            if (q['max_choices'] != null) ...[
              const SizedBox(height: 6),
              Text('Choose up to ${q['max_choices']}', style: TextStyle(color: AppColors.textMuted, fontSize: 12)),
            ],
            if (q['allow_other'] == true) ...[
              const SizedBox(height: 12),
              TextField(
                controller: _textCtrl,
                decoration: const InputDecoration(labelText: 'Others (comma-separated)', border: OutlineInputBorder()),
                onChanged: (_) => setState(() {}),
              ),
            ],
            const SizedBox(height: 6),
            Text(
              'Select none and press Next if none apply.',
              style: TextStyle(color: AppColors.textMuted, fontSize: 12),
            ),
          ],
        );
      case 'number':
        return TextField(
          controller: _textCtrl,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(
            labelText: 'Between ${q['min']} and ${q['max']}',
            border: const OutlineInputBorder(),
          ),
          onChanged: (_) => setState(() {}),
        );
      case 'text':
        return TextField(
          controller: _textCtrl,
          maxLength: q['max_length'] as int?,
          decoration: const InputDecoration(border: OutlineInputBorder()),
          onChanged: (_) => setState(() {}),
        );
      case 'rating':
        final scale = (q['scale'] as List).cast<String>();
        return Column(
          children: [
            for (final skill in (q['items'] as List).cast<String>())
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(skill, style: const TextStyle(fontWeight: FontWeight.w600)),
                    const SizedBox(height: 6),
                    SegmentedButton<String>(
                      segments: [
                        for (final l in scale)
                          ButtonSegment(value: l, label: Text(l[0].toUpperCase() + l.substring(1))),
                      ],
                      emptySelectionAllowed: true,
                      selected: {if (_rating[skill] != null) _rating[skill]!},
                      onSelectionChanged: (s) => setState(() {
                        if (s.isEmpty) {
                          _rating.remove(skill);
                        } else {
                          _rating[skill] = s.first;
                        }
                      }),
                    ),
                  ],
                ),
              ),
          ],
        );
    }
    return Text('Unsupported question type: ${q['type']}');
  }
}
