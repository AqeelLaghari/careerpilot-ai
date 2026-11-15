import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../services/api_client.dart';
import '../../theme.dart';
import 'resume_widgets.dart';

/// "Improve your bullet points" (Day 24): the CV's bullets, weak ones first. "Improve with AI"
/// asks the backend for stronger versions of ONE bullet (only when clicked, to save quota).
class BulletCoach extends StatefulWidget {
  const BulletCoach({super.key});

  @override
  State<BulletCoach> createState() => _BulletCoachState();
}

class _BulletCoachState extends State<BulletCoach> {
  static const _firstShown = 5;
  List<Map<String, dynamic>>? _bullets;
  bool _failed = false;
  bool _showAll = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await api.get('/resume/bullets');
      final list = (r['bullets'] as List).cast<Map<String, dynamic>>();
      // weak ones first (most problems first), strong ones after
      list.sort((a, b) => (b['issues'] as List).length.compareTo((a['issues'] as List).length));
      if (mounted) setState(() => _bullets = list);
    } catch (_) {
      if (mounted) setState(() => _failed = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final bullets = _bullets;
    if (_failed) return const SizedBox.shrink();
    if (bullets == null) {
      return const SectionCard(
        title: 'Improve your bullet points',
        icon: Icons.auto_awesome_outlined,
        child: LinearProgressIndicator(),
      );
    }
    if (bullets.isEmpty) return const SizedBox.shrink();
    final weak = bullets.where((b) => b['weak'] == true).length;
    final shown = _showAll ? bullets : bullets.take(_firstShown).toList();
    return SectionCard(
      title: 'Improve your bullet points',
      icon: Icons.auto_awesome_outlined,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            weak == 0
                ? 'All ${bullets.length} bullets look strong. You can still ask the AI for alternatives.'
                : '$weak of ${bullets.length} bullets could be stronger. Click "Improve with AI" on any of them.',
            style: TextStyle(color: AppColors.textMuted, fontSize: 13, height: 1.4),
          ),
          const SizedBox(height: 8),
          for (final b in shown) _BulletRow(key: ValueKey(b['text']), bullet: b),
          if (bullets.length > _firstShown)
            TextButton.icon(
              onPressed: () => setState(() => _showAll = !_showAll),
              icon: Icon(_showAll ? Icons.expand_less : Icons.expand_more),
              label: Text(_showAll ? 'Show fewer' : 'Show all ${bullets.length} bullets'),
            ),
        ],
      ),
    );
  }
}

class _BulletRow extends StatefulWidget {
  const _BulletRow({super.key, required this.bullet});
  final Map<String, dynamic> bullet;

  @override
  State<_BulletRow> createState() => _BulletRowState();
}

class _BulletRowState extends State<_BulletRow> {
  bool _busy = false;
  Map<String, dynamic>? _result;
  String? _error;

  Future<void> _improve() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final r = await api.post('/resume/rewrite', {'bullet': widget.bullet['text']});
      if (mounted) setState(() => _result = r);
    } catch (e) {
      if (mounted) setState(() => _error = 'Could not get suggestions right now. Please try again.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _copy(String text) {
    Clipboard.setData(ClipboardData(text: text));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Copied. Paste it into your CV and replace any X with your real number.')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final issues = (widget.bullet['issues'] as List).cast<String>();
    final result = _result;
    return Container(
      margin: const EdgeInsets.only(top: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        border: Border.all(color: AppColors.border),
        borderRadius: BorderRadius.circular(AppSizes.radius),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('${widget.bullet['text']}', style: TextStyle(color: AppColors.text, fontSize: 13.5, height: 1.4)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              if (issues.isEmpty)
                _issue('Looks strong', AppColors.good, Icons.check)
              else
                for (final i in issues) _issue(i, AppColors.warn, Icons.info_outline),
            ],
          ),
          const SizedBox(height: 6),
          if (result == null)
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                onPressed: _busy ? null : _improve,
                icon: _busy
                    ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.auto_awesome, size: 18),
                label: Text(_busy ? 'Improving…' : 'Improve with AI'),
              ),
            ),
          if (_error != null) Text(_error!, style: TextStyle(color: AppColors.bad, fontSize: 12.5)),
          if (result != null) ...[
            const SizedBox(height: 6),
            Text(
              result['source'] == 'ai' ? 'Suggested versions' : 'Quick fix (the AI is busy, so simple rules were used)',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: AppColors.textMuted),
            ),
            for (final v in (result['versions'] as List).cast<String>())
              Container(
                margin: const EdgeInsets.only(top: 8),
                padding: const EdgeInsets.fromLTRB(12, 10, 4, 10),
                decoration: BoxDecoration(
                  color: AppColors.brandTint,
                  borderRadius: BorderRadius.circular(AppSizes.radius),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: SelectableText(v, style: TextStyle(color: AppColors.text, fontSize: 13.5, height: 1.4)),
                    ),
                    IconButton(tooltip: 'Copy', onPressed: () => _copy(v), icon: const Icon(Icons.copy, size: 18)),
                  ],
                ),
              ),
            if ('${result['tip'] ?? ''}'.isNotEmpty) ...[
              const SizedBox(height: 8),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.tips_and_updates_outlined, size: 16, color: AppColors.brandSoft),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      '${result['tip']}',
                      style: TextStyle(fontSize: 12.5, color: AppColors.textMuted, height: 1.4),
                    ),
                  ),
                ],
              ),
            ],
            if ((result['versions'] as List).any((v) => RegExp(r'\bX\b').hasMatch('$v')))
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text(
                  'X marks a number only you know: replace it with your real figure.',
                  style: TextStyle(fontSize: 12, color: AppColors.textFaint),
                ),
              ),
          ],
        ],
      ),
    );
  }

  Widget _issue(String text, Color colour, IconData icon) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
    decoration: BoxDecoration(color: colour.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(20)),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 13, color: colour),
        const SizedBox(width: 4),
        Text(
          text,
          style: TextStyle(fontSize: 11.5, color: colour, fontWeight: FontWeight.w600),
        ),
      ],
    ),
  );
}
