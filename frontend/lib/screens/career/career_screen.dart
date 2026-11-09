import 'package:flutter/material.dart';

import '../../services/api_client.dart';
import '../../theme.dart';
import '../resume/resume_widgets.dart';
import 'career_widgets.dart';
import 'questionnaire_screen.dart';

/// Career Guide: questionnaire → best-fit careers → target role → roadmap summary → JD match.
class CareerScreen extends StatefulWidget {
  const CareerScreen({super.key});

  @override
  State<CareerScreen> createState() => _CareerScreenState();
}

class _CareerScreenState extends State<CareerScreen> {
  bool _loading = true;
  bool _noResume = false;
  String? _error;
  Map<String, dynamic>? _career;
  Map<String, dynamic>? _quiz;
  Map<String, dynamic>? _roadmap;
  bool _buildingRoadmap = false;
  String? _busyRole; // role being set as target

  @override
  void initState() {
    super.initState();
    _load();
  }

  String _clean(Object e) => '$e'.replaceFirst('Exception: ', '').replaceFirst(RegExp(r'API error \d+: '), '');

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      // Recompute matches each time: cheap (~50 ms) and always fresh after a new resume upload.
      final career = await api.post('/career/match', {});
      final quiz = await api.get('/questionnaire');
      final roadmap = await api.getOrNull('/roadmap');
      if (!mounted) return;
      setState(() {
        _career = career;
        _quiz = quiz;
        _roadmap = roadmap;
        _noResume = false;
      });
    } catch (e) {
      if (!mounted) return;
      final msg = _clean(e);
      setState(() => msg.toLowerCase().contains('upload a resume') ? _noResume = true : _error = msg);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _openQuestionnaire() async {
    final changed = await Navigator.push<bool>(
        context, MaterialPageRoute(builder: (_) => const QuestionnaireScreen()));
    if (changed == true) _load();
  }

  Future<void> _setTarget(String role) async {
    setState(() => _busyRole = role);
    try {
      final c = await api.post('/career/target', {'role': role});
      if (mounted) setState(() => _career = c);
      _snack('Target role set to ${c['target_role']}');
    } catch (e) {
      _snack(_clean(e));
    } finally {
      if (mounted) setState(() => _busyRole = null);
    }
  }

  Future<void> _pickOtherRole() async {
    final role = await showDialog<String>(context: context, builder: (_) => const RoleSearchDialog());
    if (role != null) _setTarget(role);
  }

  Future<void> _buildRoadmap() async {
    setState(() => _buildingRoadmap = true);
    try {
      final r = await api.post('/roadmap', {});
      if (mounted) setState(() => _roadmap = r);
    } catch (e) {
      _snack(_clean(e));
    } finally {
      if (mounted) setState(() => _buildingRoadmap = false);
    }
  }

  void _snack(String msg) {
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_noResume) {
      return const EmptyHint(
        icon: Icons.upload_file,
        title: 'Upload your resume first',
        text: 'Open the Resume tab and upload your CV. Your career matches and roadmap are built from it.',
      );
    }
    if (_error != null) {
      return EmptyHint(
        icon: Icons.cloud_off,
        title: 'Could not load your career data',
        text: _error!,
        action: FilledButton(onPressed: _load, child: const Text('Try again')),
      );
    }

    final matches = ((_career?['matches'] as List?) ?? []).cast<Map<String, dynamic>>();
    final target = _career?['target_role'] as String?;
    final targetMatch = _career?['target_match'] as Map<String, dynamic>?;
    final wide = MediaQuery.sizeOf(context).width > 900;

    final left = <Widget>[
      if (_quiz != null && _quiz!['completed'] != true)
        QuestionnaireBanner(
          remaining: (_quiz!['progress'] as Map)['remaining'] as int,
          answered: (_quiz!['progress'] as Map)['answered'] as int,
          onStart: _openQuestionnaire,
        ),
      SectionCard(
        title: 'Your target role',
        icon: Icons.flag_outlined,
        trailing: TextButton(onPressed: _pickOtherRole, child: Text(target == null ? 'Choose' : 'Change')),
        child: target == null
            ? const Text('Not chosen yet. Pick one of your best-fit careers below, or search any role.')
            : TargetSummary(match: targetMatch),
      ),
      SectionCard(
        title: 'Best-fit careers',
        icon: Icons.explore_outlined,
        child: matches.isEmpty
            ? const Text('No matches yet.')
            : Column(children: [
                for (final (i, m) in matches.indexed)
                  CareerMatchTile(
                    rank: i + 1,
                    match: m,
                    isTarget: m['role'] == target,
                    busy: _busyRole == m['role'],
                    onSetTarget: () => _setTarget(m['role'] as String),
                  ),
              ]),
      ),
    ];
    final right = <Widget>[
      RoadmapSummaryCard(roadmap: _roadmap, building: _buildingRoadmap, onBuild: _buildRoadmap),
      const JobDescriptionCard(),
    ];

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(padding: const EdgeInsets.all(16), children: [
        if (wide)
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Expanded(child: Column(children: left)),
            const SizedBox(width: 16),
            Expanded(child: Column(children: right)),
          ])
        else ...[...left, ...right],
        if (_quiz != null && _quiz!['completed'] == true)
          Align(
            alignment: Alignment.centerRight,
            child: TextButton.icon(
              onPressed: () async {
                await api.delete('/questionnaire');
                _openQuestionnaire();
              },
              icon: const Icon(Icons.restart_alt, size: 18),
              label: const Text('Redo the questionnaire'),
            ),
          ),
      ]),
    );
  }
}

/// Centered icon + message, for empty and error states.
class EmptyHint extends StatelessWidget {
  const EmptyHint({super.key, required this.icon, required this.title, required this.text, this.action});
  final IconData icon;
  final String title;
  final String text;
  final Widget? action;

  @override
  Widget build(BuildContext context) => Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 480),
            child: Column(children: [
              Icon(icon, size: 72, color: AppColors.brand.withValues(alpha: 0.7)),
              const SizedBox(height: 16),
              Text(title, style: Theme.of(context).textTheme.headlineSmall, textAlign: TextAlign.center),
              const SizedBox(height: 8),
              Text(text, textAlign: TextAlign.center),
              if (action != null) ...[const SizedBox(height: 16), action!],
            ]),
          ),
        ),
      );
}
