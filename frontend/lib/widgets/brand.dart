import 'dart:async';

import 'package:flutter/material.dart';

import '../theme.dart';

/// The CareerPilot AI logo (files in assets/branding, made from the originals in /branding).
class BrandLogo extends StatelessWidget {
  /// The "C" mark alone (square).
  const BrandLogo.icon({super.key, this.size = 40, this.white = false}) : horizontal = false;

  /// The mark + "CareerPilot AI" text; [size] is the height.
  const BrandLogo.horizontal({super.key, this.size = 32, this.white = false}) : horizontal = true;

  final double size;
  final bool white; // for dark backgrounds
  final bool horizontal;

  @override
  Widget build(BuildContext context) {
    final name = horizontal ? 'logo_horizontal' : 'logo_icon';
    return Image.asset(
      'assets/branding/$name${white ? '_white' : ''}.png',
      height: size,
      width: horizontal ? null : size,
      fit: BoxFit.contain,
      filterQuality: FilterQuality.medium,
      semanticLabel: 'CareerPilot AI',
    );
  }
}

/// The branded loading screen: logo, a slim progress bar, and, if it takes a while, a line
/// explaining why (the server loads its AI models on its first start). It looks the same as
/// the web start screen in web/index.html, so the change from one to the other is seamless.
class BrandLoading extends StatefulWidget {
  const BrandLoading({super.key, this.message});
  final String? message;

  @override
  State<BrandLoading> createState() => _BrandLoadingState();
}

class _BrandLoadingState extends State<BrandLoading> {
  bool _slow = false;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer(const Duration(seconds: 6), () {
      if (mounted) setState(() => _slow = true);
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final width = (MediaQuery.sizeOf(context).width * 0.7).clamp(200.0, 340.0);
    return Scaffold(
      backgroundColor: Colors.white,
      body: Center(
        child: TweenAnimationBuilder<double>(
          tween: Tween(begin: 0, end: 1),
          duration: const Duration(milliseconds: 500),
          builder: (context, t, child) => Opacity(opacity: t, child: child),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox(
                width: width,
                child: BrandLogo.horizontal(size: width * 0.232),
              ),
              const SizedBox(height: 28),
              SizedBox(
                width: width * 0.55,
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    minHeight: 4,
                    color: AppColors.navy, // the splash is always white, so fixed colours
                    backgroundColor: AppColors.navy.withValues(alpha: 0.1),
                  ),
                ),
              ),
              const SizedBox(height: 18),
              AnimatedOpacity(
                opacity: _slow || widget.message != null ? 1 : 0,
                duration: const Duration(milliseconds: 400),
                child: Text(
                  widget.message ?? 'Starting the AI engine… the first start can take up to a minute.',
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Color(0xFF5B6B82), fontSize: 13),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
