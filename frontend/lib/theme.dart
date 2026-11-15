import 'package:flutter/material.dart';

/// One place for the app's look. Every screen uses these colours and shapes.
class AppColors {
  static const brand = Color(0xFF011A42); // the logo's navy (branding/LogoPNG.png)
  static const brandMid = Color(0xFF0F2F66); // lighter navy for gradients
  static const brandLight = Color(0xFF1D4E89);
  static const good = Color(0xFF16A34A);
  static const warn = Color(0xFFF59E0B);
  static const bad = Color(0xFFDC2626);

  /// Colour for a 0–100 score.
  static Color forScore(num score) => score >= 85
      ? good
      : score >= 70
      ? const Color(0xFF65A30D)
      : score >= 50
      ? warn
      : bad;

  static Color forSeverity(String s) => switch (s) {
    'high' => bad,
    'medium' => warn,
    _ => const Color(0xFF64748B),
  };
}

ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(seedColor: AppColors.brand);
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: const Color(0xFFF6F7FB),
    appBarTheme: AppBarTheme(backgroundColor: AppColors.brand, foregroundColor: Colors.white, centerTitle: false),
    cardTheme: CardThemeData(
      elevation: 0,
      color: Colors.white,
      margin: const EdgeInsets.symmetric(vertical: 6),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: Colors.grey.shade200),
      ),
    ),
    chipTheme: ChipThemeData(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      side: BorderSide.none,
    ),
  );
}
