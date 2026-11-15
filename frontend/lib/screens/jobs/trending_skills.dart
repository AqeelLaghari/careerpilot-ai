import 'package:flutter/material.dart';

import '../../services/api_client.dart';
import '../../theme.dart';
import 'learned_skills_screen.dart';

/// "Skills in demand right now": learned weekly from live job postings, newer ones count more.
/// Admins also get a button to manage the skills the app learned on its own.
class TrendingSkills extends StatefulWidget {
  const TrendingSkills({super.key, required this.userSkills});
  final Set<String> userSkills; // lower-case names the user already has

  @override
  State<TrendingSkills> createState() => _TrendingSkillsState();
}

class _TrendingSkillsState extends State<TrendingSkills> {
  Map<String, dynamic>? _t;
  bool _admin = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final t = await api.get('/market/trending');
      final me = await api.get('/market/admin/me');
      if (mounted) {
        setState(() {
          _t = t;
          _admin = me['is_admin'] == true;
        });
      }
    } catch (_) {
      // Trends are extra information: the jobs list works without them.
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = _t;
    if (t == null) return const SizedBox.shrink();
    final top = ((t['top'] as List?) ?? []).cast<Map<String, dynamic>>();
    final rising = ((t['rising'] as List?) ?? []).cast<Map<String, dynamic>>();
    final newSkills = ((t['new_skills'] as List?) ?? []).cast<String>();
    if (top.isEmpty && !_admin) return const SizedBox.shrink();
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ExpansionTile(
        leading: const Icon(Icons.trending_up),
        title: const Text('Skills in demand right now'),
        subtitle: Text(
          top.isEmpty ? 'Learning from new job postings…' : 'From ${t['postings']} recent job postings, updated weekly',
        ),
        childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
        expandedCrossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (top.isNotEmpty) ...[
            const Text(
              'Most asked for (newer postings count more). ✓ = you have it',
              style: TextStyle(color: Colors.grey, fontSize: 12),
            ),
            const SizedBox(height: 6),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final s in top.take(15))
                  Chip(
                    visualDensity: VisualDensity.compact,
                    avatar: widget.userSkills.contains((s['name'] as String).toLowerCase())
                        ? Icon(Icons.check, size: 14, color: AppColors.good)
                        : null,
                    label: Text('${s['name']} · ${s['share']}%', style: const TextStyle(fontSize: 12)),
                  ),
              ],
            ),
          ],
          const SizedBox(height: 10),
          if (rising.isNotEmpty) ...[
            const Text('Rising fast', style: TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 6),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final s in rising.take(8))
                  Chip(
                    visualDensity: VisualDensity.compact,
                    avatar: Icon(Icons.arrow_upward, size: 14, color: AppColors.good),
                    label: Text('${s['name']} +${s['change']}%', style: const TextStyle(fontSize: 12)),
                  ),
              ],
            ),
          ] else if (top.isNotEmpty && t['history_ready'] != true)
            const Text(
              'Rising and falling skills appear after a few weeks of postings.',
              style: TextStyle(color: Colors.grey, fontSize: 12),
            ),
          if (newSkills.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(
              'New skills the app learned this week: ${newSkills.take(10).join(', ')}',
              style: const TextStyle(fontSize: 12),
            ),
          ],
          if (_admin)
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                icon: const Icon(Icons.admin_panel_settings_outlined, size: 18),
                label: const Text('Manage learned skills'),
                onPressed: () async {
                  await Navigator.of(context).push(MaterialPageRoute(builder: (_) => const LearnedSkillsScreen()));
                  _load();
                },
              ),
            ),
        ],
      ),
    );
  }
}
