import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../services/api_client.dart';
import '../services/profile_store.dart';
import '../theme.dart';
import '../widgets/skeleton.dart';

/// The dashboard (Day 24): the orchestrator's summary of everything the agents know.
///   - "Your next step": the single most useful thing to do now
///   - four score tiles: ATS, career match, roadmap, interviews
///   - ATS score history chart, recent activity
/// Refreshes each time it is opened, every minute while open, and on pull-down.
class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key, required this.onOpen});

  /// Switch to another tab ("resume", "career", "jobs", "interview").
  final ValueChanged<String> onOpen;

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  Map<String, dynamic>? _data;
  Object? _error;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(const Duration(seconds: 60), (_) => _load());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final d = await api.get('/dashboard');
      if (mounted) {
        setState(() {
          _data = d;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  String get _greeting {
    final h = DateTime.now().hour;
    final part = h < 12
        ? 'Good morning'
        : h < 17
        ? 'Good afternoon'
        : 'Good evening';
    return '$part, ${profileStore.firstName}';
  }

  @override
  Widget build(BuildContext context) {
    final data = _data;
    return RefreshIndicator(
      onRefresh: _load,
      child: LayoutBuilder(
        builder: (context, box) {
          final pad = box.maxWidth >= 700 ? 32.0 : 16.0;
          return ListView(
            padding: EdgeInsets.fromLTRB(pad, 28, pad, 40),
            children: [
              Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 1120),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  _greeting,
                                  style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700, color: AppColors.text),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  "Here's where you are on your career journey.",
                                  style: TextStyle(color: AppColors.textMuted, fontSize: 14),
                                ),
                              ],
                            ),
                          ),
                          IconButton(tooltip: 'Refresh', onPressed: _load, icon: const Icon(Icons.refresh)),
                        ],
                      ),
                      const SizedBox(height: 24),
                      if (data == null && _error != null)
                        _ErrorCard(onRetry: _load)
                      else if (data == null)
                        const _DashboardSkeleton()
                      else
                        _Content(data: data, onOpen: widget.onOpen, width: box.maxWidth - 2 * pad),
                    ],
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _Content extends StatelessWidget {
  const _Content({required this.data, required this.onOpen, required this.width});
  final Map<String, dynamic> data;
  final ValueChanged<String> onOpen;
  final double width;

  @override
  Widget build(BuildContext context) {
    final tiles = (data['tiles'] as Map).cast<String, dynamic>();
    final history = ((data['ats_history'] as List?) ?? []).cast<Map>();
    final activity = ((data['activity'] as List?) ?? []).cast<Map>();
    final columns = width >= 960
        ? 4
        : width >= 520
        ? 2
        : 1;
    final wideBottom = width >= 900;
    final chart = _Panel(
      title: 'ATS score history',
      subtitle: 'Your CV score each time you uploaded it',
      child: _AtsChart(points: history, height: wideBottom ? 300 : 220),
    );
    final recent = _Panel(
      title: 'Recent activity',
      child: _Activity(items: activity.take(_activityShown).toList()),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _NextStep(step: (data['next_step'] as Map).cast<String, dynamic>(), onOpen: onOpen),
        const SizedBox(height: 20),
        _Grid(
          columns: columns,
          children: [
            _AtsTile(t: tiles['ats'] as Map?, onTap: () => onOpen('resume')),
            _MatchTile(t: tiles['match'] as Map?, onTap: () => onOpen('career')),
            _RoadmapTile(t: tiles['roadmap'] as Map?, onTap: () => onOpen('career')),
            _InterviewTile(t: (tiles['interviews'] as Map?) ?? {}, onTap: () => onOpen('interview')),
          ],
        ),
        const SizedBox(height: 20),
        if (wideBottom)
          IntrinsicHeight(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(flex: 3, child: chart),
                const SizedBox(width: 16),
                Expanded(flex: 2, child: recent),
              ],
            ),
          )
        else ...[
          chart,
          const SizedBox(height: 16),
          recent,
        ],
      ],
    );
  }
}

/// Equal-width tiles in rows of [columns].
class _Grid extends StatelessWidget {
  const _Grid({required this.columns, required this.children});
  final int columns;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    const gap = 16.0;
    final rows = <Widget>[];
    for (var i = 0; i < children.length; i += columns) {
      final row = children.sublist(i, math.min(i + columns, children.length));
      rows.add(
        IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              for (var j = 0; j < columns; j++) ...[
                if (j > 0) const SizedBox(width: gap),
                Expanded(child: j < row.length ? row[j] : const SizedBox()),
              ],
            ],
          ),
        ),
      );
    }
    return Column(
      children: [
        for (var i = 0; i < rows.length; i++) ...[if (i > 0) const SizedBox(height: gap), rows[i]],
      ],
    );
  }
}

// ------------------------------------------------------------------ next step --
class _NextStep extends StatelessWidget {
  const _NextStep({required this.step, required this.onOpen});
  final Map<String, dynamic> step;
  final ValueChanged<String> onOpen;

  @override
  Widget build(BuildContext context) {
    final narrow = MediaQuery.sizeOf(context).width < 600;
    final button = FilledButton.icon(
      style: FilledButton.styleFrom(backgroundColor: Colors.white, foregroundColor: AppColors.navy),
      onPressed: () => onOpen('${step['tab']}'),
      icon: const Icon(Icons.arrow_forward, size: 18),
      label: Text('${step['action']}'),
    );
    final text = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'YOUR NEXT STEP',
          style: TextStyle(
            color: Colors.white.withValues(alpha: 0.65),
            fontSize: 11.5,
            fontWeight: FontWeight.w700,
            letterSpacing: 1.1,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          '${step['title']}',
          style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 6),
        Text(
          '${step['text']}',
          style: TextStyle(color: Colors.white.withValues(alpha: 0.8), fontSize: 14, height: 1.45),
        ),
      ],
    );
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(AppSizes.radiusLarge),
        gradient: const LinearGradient(
          colors: [AppColors.navy, AppColors.navyMid],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      child: narrow
          ? Column(crossAxisAlignment: CrossAxisAlignment.start, children: [text, const SizedBox(height: 18), button])
          : Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(AppSizes.radius),
                  ),
                  child: const Icon(Icons.flag_outlined, color: Colors.white, size: 26),
                ),
                const SizedBox(width: 18),
                Expanded(child: text),
                const SizedBox(width: 24),
                button,
              ],
            ),
    );
  }
}

// ---------------------------------------------------------------------- tiles --
class _Tile extends StatelessWidget {
  const _Tile({
    required this.icon,
    required this.label,
    required this.value,
    required this.onTap,
    this.unit,
    this.badge,
    this.progress,
    this.caption,
  });
  final IconData icon;
  final String label, value;
  final String? unit, caption;
  final Widget? badge;
  final double? progress;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Card(
    margin: EdgeInsets.zero,
    clipBehavior: Clip.antiAlias,
    child: InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, size: 18, color: AppColors.brandSoft),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    label,
                    style: TextStyle(color: AppColors.textMuted, fontSize: 13, fontWeight: FontWeight.w600),
                  ),
                ),
                Icon(Icons.chevron_right, size: 18, color: AppColors.textFaint),
              ],
            ),
            const SizedBox(height: 14),
            Row(
              crossAxisAlignment: CrossAxisAlignment.baseline,
              textBaseline: TextBaseline.alphabetic,
              children: [
                Flexible(
                  child: Text(
                    value,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 30, fontWeight: FontWeight.w700, color: AppColors.text, height: 1.1),
                  ),
                ),
                if (unit != null) ...[
                  const SizedBox(width: 3),
                  Text(unit!, style: TextStyle(fontSize: 14, color: AppColors.textFaint)),
                ],
                if (badge != null) ...[const SizedBox(width: 10), badge!],
              ],
            ),
            if (progress != null) ...[
              const SizedBox(height: 12),
              ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(value: progress!.clamp(0, 1), minHeight: 6),
              ),
            ],
            if (caption != null) ...[
              const SizedBox(height: 10),
              Text(
                caption!,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(fontSize: 12.5, color: AppColors.textMuted, height: 1.35),
              ),
            ],
          ],
        ),
      ),
    ),
  );
}

/// A small status label: colour + words (never colour alone).
class _Badge extends StatelessWidget {
  const _Badge(this.text, this.colour, {this.icon});
  final String text;
  final Color colour;
  final IconData? icon;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
    decoration: BoxDecoration(color: colour.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(20)),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (icon != null) ...[Icon(icon, size: 13, color: colour), const SizedBox(width: 3)],
        Text(
          text,
          style: TextStyle(fontSize: 11.5, fontWeight: FontWeight.w700, color: colour),
        ),
      ],
    ),
  );
}

class _AtsTile extends StatelessWidget {
  const _AtsTile({required this.t, required this.onTap});
  final Map? t;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final t = this.t;
    if (t == null) {
      return _Tile(
        icon: Icons.fact_check_outlined,
        label: 'ATS score',
        value: '–',
        caption: 'Upload your CV to get your score.',
        onTap: onTap,
      );
    }
    final score = t['score'] as num;
    final change = t['change'] as num?;
    return _Tile(
      icon: Icons.fact_check_outlined,
      label: 'ATS score',
      value: '$score',
      unit: '/100',
      badge: _Badge('${t['grade']}', AppColors.forScore(score)),
      progress: score / 100,
      caption: change == null || change == 0
          ? (change == 0 ? 'Same as your last upload.' : 'Upload an improved CV to track progress.')
          : '${change > 0 ? '+' : ''}$change since your last upload.',
      onTap: onTap,
    );
  }
}

class _MatchTile extends StatelessWidget {
  const _MatchTile({required this.t, required this.onTap});
  final Map? t;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final t = this.t;
    if (t == null) {
      return _Tile(
        icon: Icons.explore_outlined,
        label: 'Career match',
        value: '–',
        caption: 'Find the careers that fit your skills.',
        onTap: onTap,
      );
    }
    final score = (t['score'] as num?) ?? 0;
    return _Tile(
      icon: Icons.explore_outlined,
      label: t['basis'] == 'target' ? 'Target role match' : 'Best-fit career',
      value: '${score.round()}',
      unit: '%',
      progress: score / 100,
      caption: '${t['role']}',
      onTap: onTap,
    );
  }
}

class _RoadmapTile extends StatelessWidget {
  const _RoadmapTile({required this.t, required this.onTap});
  final Map? t;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final t = this.t;
    if (t == null) {
      return _Tile(
        icon: Icons.route_outlined,
        label: 'Roadmap',
        value: '–',
        caption: 'Build a week-by-week learning plan.',
        onTap: onTap,
      );
    }
    final status = '${t['status']}';
    final (badgeText, colour, icon) = switch (status) {
      'behind' => ('Behind', AppColors.warn, Icons.schedule),
      'ahead' => ('Ahead', AppColors.good, Icons.trending_up),
      'done' => ('Done', AppColors.good, Icons.check_circle_outline),
      _ => ('On track', AppColors.good, Icons.check),
    };
    return _Tile(
      icon: Icons.route_outlined,
      label: 'Roadmap progress',
      value: '${t['percent']}',
      unit: '%',
      badge: _Badge(badgeText, colour, icon: icon),
      progress: (t['percent'] as num) / 100,
      caption: '${t['tasks_done']} of ${t['tasks_total']} tasks done',
      onTap: onTap,
    );
  }
}

class _InterviewTile extends StatelessWidget {
  const _InterviewTile({required this.t, required this.onTap});
  final Map t;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final count = (t['count'] as num?) ?? 0;
    if (count == 0) {
      return _Tile(
        icon: Icons.videocam_outlined,
        label: 'Mock interviews',
        value: '0',
        caption: 'Practise with the AI interviewer.',
        onTap: onTap,
      );
    }
    final avg = (t['average'] ?? t['last']) as num;
    return _Tile(
      icon: Icons.videocam_outlined,
      label: 'Average interview score',
      value: '$avg',
      unit: '/100',
      badge: _Badge(
        avg >= 70
            ? 'Strong'
            : avg >= 50
            ? 'Fair'
            : 'Keep practising',
        AppColors.forScore(avg),
      ),
      progress: avg / 100,
      caption: '$count interview${count == 1 ? '' : 's'} · best ${t['best']} · last ${t['last']}',
      onTap: onTap,
    );
  }
}

// ---------------------------------------------------------------- panels --
/// Recent activity rows on the dashboard: 5 fill about the same height as the chart next to them.
const _activityShown = 5;

class _Panel extends StatelessWidget {
  const _Panel({required this.title, required this.child, this.subtitle});
  final String title;
  final String? subtitle;
  final Widget child;

  @override
  Widget build(BuildContext context) => Card(
    margin: EdgeInsets.zero,
    child: Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: TextStyle(fontSize: 15.5, fontWeight: FontWeight.w700, color: AppColors.text),
          ),
          if (subtitle != null) ...[
            const SizedBox(height: 2),
            Text(subtitle!, style: TextStyle(fontSize: 12.5, color: AppColors.textMuted)),
          ],
          const SizedBox(height: 16),
          child,
        ],
      ),
    ),
  );
}

class _Empty extends StatelessWidget {
  const _Empty({required this.icon, required this.text});
  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 28),
    child: Center(
      child: Column(
        children: [
          Icon(icon, size: 34, color: AppColors.textFaint),
          const SizedBox(height: 10),
          Text(
            text,
            textAlign: TextAlign.center,
            style: TextStyle(color: AppColors.textMuted, fontSize: 13, height: 1.4),
          ),
        ],
      ),
    ),
  );
}

const _months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

DateTime? _time(Object? seconds) =>
    seconds is num ? DateTime.fromMillisecondsSinceEpoch((seconds * 1000).round()) : null;

String _date(DateTime d) => '${d.day} ${_months[d.month - 1]}';

String _ago(DateTime d) {
  final s = DateTime.now().difference(d);
  if (s.inMinutes < 1) return 'just now';
  if (s.inMinutes < 60) return '${s.inMinutes} min ago';
  if (s.inHours < 24) return '${s.inHours} h ago';
  if (s.inDays < 7) return '${s.inDays} d ago';
  return _date(d);
}

class _Activity extends StatelessWidget {
  const _Activity({required this.items});
  final List<Map> items;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return const _Empty(icon: Icons.history, text: 'Nothing yet. What you do in the app shows up here.');
    }
    return Column(
      children: [
        for (final item in items)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 7),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  padding: const EdgeInsets.all(7),
                  decoration: BoxDecoration(color: AppColors.brandTint, borderRadius: BorderRadius.circular(9)),
                  child: Icon(
                    switch (item['kind']) {
                      'resume' => Icons.description_outlined,
                      'career' => Icons.flag_outlined,
                      'roadmap' => Icons.route_outlined,
                      'interview' => Icons.videocam_outlined,
                      _ => Icons.circle_outlined,
                    },
                    size: 16,
                    color: AppColors.brand,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${item['text']}', style: TextStyle(fontSize: 13.5, color: AppColors.text, height: 1.35)),
                      const SizedBox(height: 2),
                      Text(
                        _ago(_time(item['at']) ?? DateTime.now()),
                        style: TextStyle(fontSize: 11.5, color: AppColors.textFaint),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

// ----------------------------------------------------------------- the chart --
/// One line: the ATS score of each upload (evenly spaced, oldest left). Hover or tap a
/// point for its score and date.
class _AtsChart extends StatefulWidget {
  const _AtsChart({required this.points, this.height = 220});
  final List<Map> points;
  final double height;

  @override
  State<_AtsChart> createState() => _AtsChartState();
}

class _AtsChartState extends State<_AtsChart> {
  int? _hover;

  int? _nearest(Offset p, Size size) {
    final n = widget.points.length;
    if (n < 2) return null;
    final plot = _AtsPainter.plotRect(size);
    final i = ((p.dx - plot.left) / plot.width * (n - 1)).round();
    return i.clamp(0, n - 1);
  }

  @override
  Widget build(BuildContext context) {
    final pts = widget.points;
    if (pts.isEmpty) {
      return const _Empty(icon: Icons.show_chart, text: 'Upload your CV to start your score history.');
    }
    if (pts.length == 1) {
      return _Empty(
        icon: Icons.show_chart,
        text:
            'First score: ${pts.first['score']}/100.\nImprove your CV with the fixes and upload it again to see your progress here.',
      );
    }
    return SizedBox(
      height: widget.height,
      child: LayoutBuilder(
        builder: (context, box) {
          final size = Size(box.maxWidth, widget.height);
          void pick(Offset p) => setState(() => _hover = _nearest(p, size));
          return MouseRegion(
            onHover: (e) => pick(e.localPosition),
            onExit: (_) => setState(() => _hover = null),
            child: GestureDetector(
              onTapDown: (e) => pick(e.localPosition),
              onHorizontalDragUpdate: (e) => pick(e.localPosition),
              child: CustomPaint(
                size: size,
                painter: _AtsPainter(
                  scores: [for (final p in pts) (p['score'] as num).toDouble()],
                  dates: [for (final p in pts) _time(p['at'])],
                  hover: _hover,
                  line: AppColors.brand,
                  surface: AppColors.surface,
                  grid: AppColors.border,
                  text: AppColors.text,
                  muted: AppColors.textFaint,
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

class _AtsPainter extends CustomPainter {
  _AtsPainter({
    required this.scores,
    required this.dates,
    required this.hover,
    required this.line,
    required this.surface,
    required this.grid,
    required this.text,
    required this.muted,
  });
  final List<double> scores;
  final List<DateTime?> dates;
  final int? hover;
  final Color line, surface, grid, text, muted;

  static Rect plotRect(Size s) => Rect.fromLTRB(34, 20, s.width - 12, s.height - 26);

  void _label(Canvas c, String s, Offset at, Color colour, {double size = 11, bool bold = false, TextAlign? align}) {
    final tp = TextPainter(
      text: TextSpan(
        text: s,
        style: TextStyle(color: colour, fontSize: size, fontWeight: bold ? FontWeight.w700 : FontWeight.w400),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    final dx = switch (align) {
      TextAlign.right => at.dx - tp.width,
      TextAlign.center => at.dx - tp.width / 2,
      _ => at.dx,
    };
    tp.paint(c, Offset(dx, at.dy - tp.height / 2));
  }

  @override
  void paint(Canvas canvas, Size size) {
    final r = plotRect(size);
    double y(double v) => r.bottom - v / 100 * r.height;
    double x(int i) => r.left + (scores.length == 1 ? r.width / 2 : i / (scores.length - 1) * r.width);

    // recessive grid: 0, 50, 70 (the "good" line) and 100
    final gridPaint = Paint()
      ..color = grid
      ..strokeWidth = 1;
    for (final v in [0, 50, 70, 100]) {
      canvas.drawLine(Offset(r.left, y(v.toDouble())), Offset(r.right, y(v.toDouble())), gridPaint);
      _label(canvas, '$v', Offset(r.left - 8, y(v.toDouble())), muted, align: TextAlign.right);
    }
    // first and last date under the axis
    final first = dates.first, last = dates.last;
    if (first != null) _label(canvas, _date(first), Offset(r.left, r.bottom + 14), muted);
    if (last != null) _label(canvas, _date(last), Offset(r.right, r.bottom + 14), muted, align: TextAlign.right);

    // the line (2 px)
    final path = Path()..moveTo(x(0), y(scores[0]));
    for (var i = 1; i < scores.length; i++) {
      path.lineTo(x(i), y(scores[i]));
    }
    canvas.drawPath(
      path,
      Paint()
        ..color = line
        ..strokeWidth = 2
        ..style = PaintingStyle.stroke
        ..strokeJoin = StrokeJoin.round,
    );

    // crosshair for the hovered point
    if (hover != null) {
      canvas.drawLine(
        Offset(x(hover!), r.top),
        Offset(x(hover!), r.bottom),
        Paint()
          ..color = muted
          ..strokeWidth = 1,
      );
    }

    // markers: 9 px dots with a 2 px ring in the card colour
    for (var i = 0; i < scores.length; i++) {
      final c = Offset(x(i), y(scores[i]));
      final big = i == hover;
      canvas.drawCircle(c, big ? 7 : 6.5, Paint()..color = surface);
      canvas.drawCircle(c, big ? 5.5 : 4.5, Paint()..color = line);
    }

    // the latest score labelled directly (unless the tooltip is showing)
    final lastI = scores.length - 1;
    if (hover == null) {
      _label(
        canvas,
        '${scores[lastI].round()}',
        Offset(x(lastI), y(scores[lastI]) - 15),
        text,
        size: 12,
        bold: true,
        align: TextAlign.center,
      );
    } else {
      final i = hover!;
      final when = dates[i] == null ? '' : ' · ${_date(dates[i]!)}';
      final label = TextPainter(
        text: TextSpan(
          children: [
            TextSpan(
              text: '${scores[i].round()}/100',
              style: TextStyle(color: text, fontWeight: FontWeight.w700, fontSize: 12.5),
            ),
            TextSpan(
              text: '$when\nUpload ${i + 1} of ${scores.length}',
              style: TextStyle(color: muted, fontSize: 11.5, height: 1.4),
            ),
          ],
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      final w = label.width + 20, h = label.height + 14;
      var left = x(i) + 10;
      if (left + w > size.width) left = x(i) - 10 - w;
      final top = (y(scores[i]) - h - 8).clamp(0.0, size.height - h);
      final box = RRect.fromRectAndRadius(Rect.fromLTWH(left, top, w, h), const Radius.circular(8));
      canvas.drawRRect(box.shift(const Offset(0, 2)), Paint()..color = Colors.black.withValues(alpha: 0.08));
      canvas.drawRRect(box, Paint()..color = surface);
      canvas.drawRRect(
        box,
        Paint()
          ..color = grid
          ..style = PaintingStyle.stroke,
      );
      label.paint(canvas, Offset(left + 10, top + 7));
    }
  }

  @override
  bool shouldRepaint(_AtsPainter old) =>
      old.hover != hover || old.scores != scores || old.line != line || old.surface != surface;
}

// ------------------------------------------------------- loading and errors --
class _DashboardSkeleton extends StatelessWidget {
  const _DashboardSkeleton();

  @override
  Widget build(BuildContext context) => const Skeleton(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SkeletonBox(height: 128),
        SizedBox(height: 20),
        Row(
          children: [
            Expanded(child: SkeletonBox(height: 140)),
            SizedBox(width: 16),
            Expanded(child: SkeletonBox(height: 140)),
          ],
        ),
        SizedBox(height: 16),
        Row(
          children: [
            Expanded(child: SkeletonBox(height: 140)),
            SizedBox(width: 16),
            Expanded(child: SkeletonBox(height: 140)),
          ],
        ),
        SizedBox(height: 20),
        SkeletonBox(height: 260),
      ],
    ),
  );
}

class _ErrorCard extends StatelessWidget {
  const _ErrorCard({required this.onRetry});
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        children: [
          Icon(Icons.cloud_off_outlined, size: 40, color: AppColors.textFaint),
          const SizedBox(height: 12),
          Text(
            'Could not load your dashboard.',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: AppColors.text),
          ),
          const SizedBox(height: 4),
          Text('Check that the server is running, then try again.', style: TextStyle(color: AppColors.textMuted)),
          const SizedBox(height: 16),
          FilledButton.icon(onPressed: onRetry, icon: const Icon(Icons.refresh), label: const Text('Try again')),
        ],
      ),
    ),
  );
}
