import 'package:flutter/material.dart';

import '../../theme.dart';

/// Big circular score, e.g. "91 / Excellent".
class ScoreGauge extends StatelessWidget {
  const ScoreGauge({super.key, required this.score, required this.label, this.size = 140});
  final num score;
  final String label;
  final double size;

  @override
  Widget build(BuildContext context) {
    final color = AppColors.forScore(score);
    return SizedBox(
      width: size,
      height: size,
      child: TweenAnimationBuilder<double>(
        tween: Tween(begin: 0, end: score / 100),
        duration: const Duration(milliseconds: 900),
        curve: Curves.easeOutCubic,
        builder: (context, value, _) => Stack(
          fit: StackFit.expand,
          children: [
            CircularProgressIndicator(
              value: value,
              strokeWidth: 12,
              strokeCap: StrokeCap.round,
              backgroundColor: color.withValues(alpha: 0.12),
              valueColor: AlwaysStoppedAnimation(color),
            ),
            Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    '${(value * 100).round()}',
                    style: TextStyle(fontSize: size * 0.28, fontWeight: FontWeight.bold, color: color),
                  ),
                  Text(label, style: Theme.of(context).textTheme.labelLarge),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Titled white card used for every block on the resume screen.
class SectionCard extends StatelessWidget {
  const SectionCard({super.key, required this.title, required this.child, this.icon, this.trailing});
  final String title;
  final Widget child;
  final IconData? icon;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              if (icon != null) ...[Icon(icon, size: 20, color: AppColors.brand), const SizedBox(width: 8)],
              Expanded(child: Text(title, style: Theme.of(context).textTheme.titleMedium)),
              ?trailing,
            ],
          ),
          const SizedBox(height: 12),
          child,
        ],
      ),
    ),
  );
}

/// One "top fix": severity bar, the fix text, and points available.
class FixTile extends StatelessWidget {
  const FixTile({super.key, required this.fix});
  final Map<String, dynamic> fix;

  @override
  Widget build(BuildContext context) {
    final color = AppColors.forSeverity(fix['severity'] as String);
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(12),
        border: Border(left: BorderSide(color: color, width: 4)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(fix['label'] as String, style: const TextStyle(fontWeight: FontWeight.w600)),
                const SizedBox(height: 4),
                Text(fix['fix'] as String),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Chip(
            label: Text('+${fix['points_available']} pts'),
            backgroundColor: color.withValues(alpha: 0.15),
            labelStyle: TextStyle(color: color, fontWeight: FontWeight.bold, fontSize: 12),
            visualDensity: VisualDensity.compact,
          ),
        ],
      ),
    );
  }
}

/// Expandable category ("ATS parseability 28/30") listing its checks.
class CategoryTile extends StatelessWidget {
  const CategoryTile({super.key, required this.category});
  final Map<String, dynamic> category;

  @override
  Widget build(BuildContext context) {
    final score = category['score'] as num;
    final max = category['max'] as num;
    final pct = max == 0 ? 0 : score / max * 100;
    final checks = (category['checks'] as List).cast<Map<String, dynamic>>();
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      title: Text(category['name'] as String),
      subtitle: Padding(
        padding: const EdgeInsets.only(top: 6),
        child: LinearProgressIndicator(
          value: pct / 100,
          minHeight: 6,
          borderRadius: BorderRadius.circular(3),
          color: AppColors.forScore(pct),
          backgroundColor: AppColors.border,
        ),
      ),
      trailing: Text('${_fmt(score)} / ${_fmt(max)}', style: const TextStyle(fontWeight: FontWeight.bold)),
      children: [
        for (final c in checks)
          ListTile(
            contentPadding: EdgeInsets.zero,
            dense: true,
            leading: Icon(
              c['passed'] == true ? Icons.check_circle : Icons.error_outline,
              color: c['passed'] == true ? AppColors.good : AppColors.forSeverity(c['severity'] as String),
            ),
            title: Text(c['label'] as String),
            subtitle: Text(c['passed'] == true ? c['message'] as String : '${c['message']}\nFix: ${c['fix']}'),
            trailing: Text('${_fmt(c['points'])}/${_fmt(c['max_points'])}'),
          ),
      ],
    );
  }

  static String _fmt(dynamic n) => (n as num) == n.roundToDouble() ? n.round().toString() : n.toStringAsFixed(1);
}

/// Skills grouped by category as chips.
class SkillGroups extends StatelessWidget {
  const SkillGroups({super.key, required this.skills});
  final List<Map<String, dynamic>> skills;

  static String _pretty(String cat) => cat
      .split('_')
      .map((w) => w.isEmpty ? w : w[0].toUpperCase() + w.substring(1))
      .join(' ')
      .replaceAll('Ml', 'ML')
      .replaceAll('Ux', 'UX')
      .replaceAll('Ai Llm', 'AI & LLMs')
      .replaceAll('Bi', 'BI');

  @override
  Widget build(BuildContext context) {
    final groups = <String, List<Map<String, dynamic>>>{};
    for (final s in skills) {
      groups.putIfAbsent(s['category'] as String, () => []).add(s);
    }
    final ordered = groups.entries.toList()..sort((a, b) => b.value.length.compareTo(a.value.length));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final g in ordered) ...[
          Text(_pretty(g.key), style: Theme.of(context).textTheme.labelLarge?.copyWith(color: AppColors.textMuted)),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              for (final s in g.value)
                Tooltip(
                  message: 'Mentioned ${s['mentions']}× in: ${(s['sections'] as List).join(', ')}',
                  child: Chip(
                    label: Text(s['name'] as String),
                    backgroundColor: AppColors.brand.withValues(alpha: 0.08),
                    visualDensity: VisualDensity.compact,
                  ),
                ),
            ],
          ),
          const SizedBox(height: 12),
        ],
      ],
    );
  }
}

/// ATS Layer 2 + 3: how well the resume fits a role (best-fit or the user's target).
class RoleMatchCard extends StatelessWidget {
  const RoleMatchCard({super.key, required this.match});
  final Map<String, dynamic>? match;

  Widget _bar(BuildContext context, String label, num value, String hint) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(child: Text(label)),
            Text('${value.round()}%', style: const TextStyle(fontWeight: FontWeight.w600)),
          ],
        ),
        const SizedBox(height: 4),
        LinearProgressIndicator(
          value: value / 100,
          minHeight: 6,
          borderRadius: BorderRadius.circular(3),
          color: AppColors.forScore(value),
          backgroundColor: AppColors.border,
        ),
        Text(hint, style: TextStyle(fontSize: 12, color: AppColors.textMuted)),
      ],
    ),
  );

  @override
  Widget build(BuildContext context) {
    final m = match;
    if (m == null) {
      return const SectionCard(
        title: 'Role match',
        icon: Icons.track_changes,
        child: Text('Role matching is not available right now.'),
      );
    }
    final score = m['score'] as num;
    final missing = (m['missing_skills'] as List).cast<String>();
    final matched = (m['matched_skills'] as List).cast<String>();
    return SectionCard(
      title: 'Role match',
      icon: Icons.track_changes,
      trailing: Text(
        '${score.round()}%',
        style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: AppColors.forScore(score)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(m['role'] as String, style: Theme.of(context).textTheme.titleLarge),
          Text(
            '${m['basis'] == 'target role' ? 'Your target role' : 'Your best-fit role'} · '
            'learned from ${m['postings_analysed']} job postings',
            style: TextStyle(color: AppColors.textMuted),
          ),
          if (m['better_fit'] is Map) ...[
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: AppColors.brand.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                children: [
                  const Icon(Icons.lightbulb_outline, size: 18),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'This CV fits ${m['better_fit']['role']} better '
                      '(${(m['better_fit']['score'] as num).round()}%). '
                      'You can change your target role in the Career tab.',
                    ),
                  ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 12),
          _bar(context, 'Keyword match', m['keyword'] as num, 'Top skills employers ask for in this role'),
          _bar(context, 'Meaning match', m['semantic'] as num, 'How close your profile is in meaning (AI)'),
          if (missing.isNotEmpty) ...[
            const SizedBox(height: 4),
            const Text('Skills to add (if you have them):', style: TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 6),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final s in missing)
                  Chip(
                    label: Text(s, style: const TextStyle(fontSize: 12)),
                    avatar: const Icon(Icons.add, size: 16),
                    visualDensity: VisualDensity.compact,
                  ),
              ],
            ),
          ],
          if (matched.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text('Already showing: ${matched.join(', ')}', style: TextStyle(fontSize: 12, color: AppColors.textMuted)),
          ],
        ],
      ),
    );
  }
}
