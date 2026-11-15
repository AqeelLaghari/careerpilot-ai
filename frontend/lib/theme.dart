import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// The CareerPilot AI design system: ONE place for the app's look.
///
/// Rules (so every screen looks like the same product):
///   - Navy (the logo colour) is the only "action" colour: top bar, buttons, selected tabs,
///     links, icons, progress bars.
///   - Surfaces are white on a very light blue-grey background.
///   - Greys are for secondary text, borders and inactive things.
///   - Green / amber / red are used ONLY for scores and status, where colour has a meaning.
class AppColors {
  /// Set by buildTheme whenever the theme changes; the colour names below follow it.
  static bool dark = false;
  static _Palette get _p => dark ? _Palette.darkMode : _Palette.lightMode;

  // The logo navy: ALWAYS navy, in both modes (top bar, login panel, avatars, splash)
  static const navy = Color(0xFF011A42);
  static const navyMid = Color(0xFF0F2F66);
  static const navyLight = Color(0xFF1D4E89);
  static const navySoft = Color(0xFF3D6BAA);

  // The "action" colour scale: navy in light mode, soft blues in dark mode
  static Color get brand => _p.brand;
  static Color get brandMid => _p.brandMid;
  static Color get brandLight => _p.brandLight;
  static Color get brandSoft => _p.brandSoft; // icons and accents
  static Color get brandTint => _p.brandTint; // selected backgrounds, chips
  static Color get brandWash => _p.brandWash; // page background
  static Color get onBrand => _p.onBrand; // text/icons on a brand-coloured button

  // Surfaces and greys (slate)
  static Color get surface => _p.surface; // cards, sheets, menus
  static Color get text => _p.text;
  static Color get textMuted => _p.textMuted;
  static Color get textFaint => _p.textFaint;
  static Color get border => _p.border;
  static Color get borderStrong => _p.borderStrong;

  // Meaning colours: scores and status only
  static Color get good => _p.good;
  static Color get warn => _p.warn;
  static Color get bad => _p.bad;

  /// Colour for a 0-100 score.
  static Color forScore(num score) => score >= 85
      ? good
      : score >= 70
      ? _p.fair
      : score >= 50
      ? warn
      : bad;

  static Color forSeverity(String s) => switch (s) {
    'high' => bad,
    'medium' => warn,
    _ => textMuted,
  };
}

/// The two colour sets. Dark mode keeps the same layout and meaning, with soft blues as the
/// action colour (navy would disappear on a dark background).
class _Palette {
  const _Palette({
    required this.brand,
    required this.brandMid,
    required this.brandLight,
    required this.brandSoft,
    required this.brandTint,
    required this.brandWash,
    required this.onBrand,
    required this.surface,
    required this.text,
    required this.textMuted,
    required this.textFaint,
    required this.border,
    required this.borderStrong,
    required this.good,
    required this.fair,
    required this.warn,
    required this.bad,
  });

  final Color brand, brandMid, brandLight, brandSoft, brandTint, brandWash, onBrand, surface;
  final Color text, textMuted, textFaint, border, borderStrong, good, fair, warn, bad;

  static const lightMode = _Palette(
    brand: AppColors.navy,
    brandMid: AppColors.navyMid,
    brandLight: AppColors.navyLight,
    brandSoft: AppColors.navySoft,
    brandTint: Color(0xFFE8EEF8),
    brandWash: Color(0xFFF3F6FB),
    onBrand: Colors.white,
    surface: Colors.white,
    text: Color(0xFF0F172A),
    textMuted: Color(0xFF526077),
    textFaint: Color(0xFF8A96A8),
    border: Color(0xFFDCE3ED),
    borderStrong: Color(0xFFC3CDDB),
    good: Color(0xFF15803D),
    fair: Color(0xFF4D7C0F),
    warn: Color(0xFFD97706),
    bad: Color(0xFFDC2626),
  );

  static const darkMode = _Palette(
    brand: Color(0xFF9DBDF5),
    brandMid: Color(0xFFB7CEF7),
    brandLight: Color(0xFFA9C4F0),
    brandSoft: Color(0xFF86A9E3),
    brandTint: Color(0xFF1B2B4A),
    brandWash: Color(0xFF0B1220),
    onBrand: Color(0xFF011A42),
    surface: Color(0xFF131C2E),
    text: Color(0xFFE6EBF3),
    textMuted: Color(0xFFA3B0C4),
    textFaint: Color(0xFF6E7D95),
    border: Color(0xFF253350),
    borderStrong: Color(0xFF34466A),
    good: Color(0xFF4ADE80),
    fair: Color(0xFFA3E635),
    warn: Color(0xFFFBBF24),
    bad: Color(0xFFF87171),
  );
}

/// Spacing and corner sizes used everywhere.
class AppSizes {
  static const radius = 12.0;
  static const radiusLarge = 16.0;
}

ThemeData buildTheme({bool dark = false}) {
  AppColors.dark = dark;
  final scheme = ColorScheme.fromSeed(seedColor: AppColors.navy, brightness: dark ? Brightness.dark : Brightness.light)
      .copyWith(
        primary: AppColors.brand,
        onPrimary: AppColors.onBrand,
        primaryContainer: AppColors.brandTint,
        onPrimaryContainer: AppColors.brand,
        secondary: AppColors.brandLight,
        onSecondary: AppColors.onBrand,
        secondaryContainer: AppColors.brandTint,
        onSecondaryContainer: AppColors.brand,
        tertiary: AppColors.brandSoft,
        onTertiary: AppColors.onBrand,
        tertiaryContainer: AppColors.brandTint,
        onTertiaryContainer: AppColors.brand,
        error: AppColors.bad,
        onError: Colors.white,
        surface: AppColors.surface,
        onSurface: AppColors.text,
        onSurfaceVariant: AppColors.textMuted,
        surfaceContainerLowest: AppColors.surface,
        surfaceContainerLow: AppColors.brandWash,
        surfaceContainer: AppColors.brandWash,
        surfaceContainerHigh: AppColors.brandTint,
        surfaceContainerHighest: AppColors.brandTint,
        outline: AppColors.borderStrong,
        outlineVariant: AppColors.border,
        surfaceTint: Colors.transparent, // no colour wash on raised surfaces
      );

  final base = ThemeData(useMaterial3: true, colorScheme: scheme);
  final text = GoogleFonts.interTextTheme(
    base.textTheme,
  ).apply(bodyColor: AppColors.text, displayColor: AppColors.text);
  final rounded = RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppSizes.radius));
  const buttonPadding = EdgeInsets.symmetric(horizontal: 20, vertical: 16);
  final buttonText = text.labelLarge?.copyWith(fontWeight: FontWeight.w600, fontSize: 15);

  return base.copyWith(
    textTheme: text,
    scaffoldBackgroundColor: AppColors.brandWash,
    iconTheme: IconThemeData(color: AppColors.brandSoft),
    dividerTheme: DividerThemeData(color: AppColors.border, thickness: 1, space: 1),
    appBarTheme: AppBarTheme(
      backgroundColor: dark ? const Color(0xFF0A1630) : AppColors.navy,
      foregroundColor: Colors.white,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleTextStyle: text.titleLarge?.copyWith(color: Colors.white, fontWeight: FontWeight.w600),
      iconTheme: const IconThemeData(color: Colors.white),
      actionsIconTheme: const IconThemeData(color: Colors.white),
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      color: AppColors.surface,
      margin: const EdgeInsets.symmetric(vertical: 6),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppSizes.radiusLarge),
        side: BorderSide(color: AppColors.border),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: AppColors.brand,
        foregroundColor: AppColors.onBrand,
        disabledBackgroundColor: AppColors.border,
        disabledForegroundColor: AppColors.textFaint,
        padding: buttonPadding,
        shape: rounded,
        textStyle: buttonText,
      ),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: AppColors.brand,
        foregroundColor: AppColors.onBrand,
        elevation: 0,
        padding: buttonPadding,
        shape: rounded,
        textStyle: buttonText,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.brand,
        side: BorderSide(color: AppColors.borderStrong),
        padding: buttonPadding,
        shape: rounded,
        textStyle: buttonText,
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: AppColors.brandLight,
        shape: rounded,
        textStyle: text.labelLarge?.copyWith(fontWeight: FontWeight.w600),
      ),
    ),
    iconButtonTheme: IconButtonThemeData(style: IconButton.styleFrom(foregroundColor: AppColors.brandSoft)),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.surface,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      labelStyle: TextStyle(color: AppColors.textMuted),
      floatingLabelStyle: TextStyle(color: AppColors.brand, fontWeight: FontWeight.w600),
      hintStyle: TextStyle(color: AppColors.textFaint),
      prefixIconColor: WidgetStateColor.resolveWith(
        (s) => s.contains(WidgetState.focused) ? AppColors.brand : AppColors.textFaint,
      ),
      suffixIconColor: AppColors.textFaint,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppSizes.radius),
        borderSide: BorderSide(color: AppColors.borderStrong),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppSizes.radius),
        borderSide: BorderSide(color: AppColors.borderStrong),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppSizes.radius),
        borderSide: BorderSide(color: AppColors.brand, width: 2),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppSizes.radius),
        borderSide: BorderSide(color: AppColors.bad),
      ),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: AppColors.surface,
      selectedColor: AppColors.brand,
      secondarySelectedColor: AppColors.brand,
      checkmarkColor: AppColors.onBrand,
      labelStyle: text.labelLarge?.copyWith(color: AppColors.text),
      secondaryLabelStyle: text.labelLarge?.copyWith(color: AppColors.onBrand),
      side: BorderSide(color: AppColors.border),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      iconTheme: IconThemeData(color: AppColors.brandSoft, size: 18),
    ),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: ButtonStyle(
        backgroundColor: WidgetStateColor.resolveWith(
          (s) => s.contains(WidgetState.selected) ? AppColors.brand : AppColors.surface,
        ),
        foregroundColor: WidgetStateColor.resolveWith(
          (s) => s.contains(WidgetState.selected) ? AppColors.onBrand : AppColors.brand,
        ),
        iconColor: WidgetStateColor.resolveWith(
          (s) => s.contains(WidgetState.selected) ? AppColors.onBrand : AppColors.brand,
        ),
        side: WidgetStatePropertyAll(BorderSide(color: AppColors.borderStrong)),
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: AppColors.surface,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      height: 68,
      indicatorColor: AppColors.brandTint,
      iconTheme: WidgetStateProperty.resolveWith(
        (s) => IconThemeData(color: s.contains(WidgetState.selected) ? AppColors.brand : AppColors.textFaint),
      ),
      labelTextStyle: WidgetStateProperty.resolveWith(
        (s) => text.labelMedium?.copyWith(
          color: s.contains(WidgetState.selected) ? AppColors.brand : AppColors.textMuted,
          fontWeight: s.contains(WidgetState.selected) ? FontWeight.w700 : FontWeight.w500,
        ),
      ),
    ),
    navigationRailTheme: NavigationRailThemeData(
      backgroundColor: AppColors.surface,
      indicatorColor: AppColors.brandTint,
      selectedIconTheme: IconThemeData(color: AppColors.brand),
      unselectedIconTheme: IconThemeData(color: AppColors.textFaint),
      selectedLabelTextStyle: text.labelLarge?.copyWith(color: AppColors.brand, fontWeight: FontWeight.w700),
      unselectedLabelTextStyle: text.labelLarge?.copyWith(color: AppColors.textMuted),
    ),
    tabBarTheme: TabBarThemeData(
      labelColor: AppColors.brand,
      unselectedLabelColor: AppColors.textMuted,
      indicatorColor: AppColors.brand,
      dividerColor: AppColors.border,
      labelStyle: text.titleSmall?.copyWith(fontWeight: FontWeight.w700),
    ),
    listTileTheme: ListTileThemeData(iconColor: AppColors.brandSoft, textColor: AppColors.text),
    expansionTileTheme: ExpansionTileThemeData(
      iconColor: AppColors.brand,
      collapsedIconColor: AppColors.brandSoft,
      textColor: AppColors.brand,
      collapsedTextColor: AppColors.text,
    ),
    progressIndicatorTheme: ProgressIndicatorThemeData(
      color: AppColors.brand,
      linearTrackColor: AppColors.brandTint,
      circularTrackColor: Colors.transparent,
    ),
    checkboxTheme: CheckboxThemeData(
      fillColor: WidgetStateColor.resolveWith(
        (s) => s.contains(WidgetState.selected) ? AppColors.brand : AppColors.surface,
      ),
      side: BorderSide(color: AppColors.borderStrong, width: 1.5),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
    ),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStatePropertyAll(AppColors.surface),
      trackColor: WidgetStateColor.resolveWith(
        (s) => s.contains(WidgetState.selected) ? AppColors.brand : AppColors.border,
      ),
      trackOutlineColor: const WidgetStatePropertyAll(Colors.transparent),
    ),
    sliderTheme: SliderThemeData(activeTrackColor: AppColors.brand, thumbColor: AppColors.brand),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: AppColors.navy,
      contentTextStyle: text.bodyMedium?.copyWith(color: Colors.white),
      behavior: SnackBarBehavior.floating,
      shape: rounded,
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: AppColors.surface,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      titleTextStyle: text.titleLarge?.copyWith(fontWeight: FontWeight.w700),
      iconColor: AppColors.brand,
    ),
    popupMenuTheme: PopupMenuThemeData(
      color: AppColors.surface,
      surfaceTintColor: Colors.transparent,
      elevation: 8,
      shadowColor: Colors.black.withValues(alpha: dark ? 0.5 : 0.12),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppSizes.radiusLarge)),
    ),
    tooltipTheme: TooltipThemeData(
      decoration: BoxDecoration(color: AppColors.navy, borderRadius: BorderRadius.circular(8)),
      textStyle: const TextStyle(color: Colors.white, fontSize: 12),
    ),
    badgeTheme: BadgeThemeData(backgroundColor: AppColors.brand),
  );
}
