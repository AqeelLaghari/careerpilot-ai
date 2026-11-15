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
  // Navy scale, from the logo (#011A42) to light tints
  static const brand = Color(0xFF011A42); // the logo's navy
  static const brandMid = Color(0xFF0F2F66);
  static const brandLight = Color(0xFF1D4E89);
  static const brandSoft = Color(0xFF3D6BAA); // icons and accents on white
  static const brandTint = Color(0xFFE8EEF8); // selected backgrounds, chips
  static const brandWash = Color(0xFFF3F6FB); // page background

  // Greys (slate)
  static const text = Color(0xFF0F172A);
  static const textMuted = Color(0xFF526077);
  static const textFaint = Color(0xFF8A96A8);
  static const border = Color(0xFFDCE3ED);
  static const borderStrong = Color(0xFFC3CDDB);

  // Meaning colours: scores and status only
  static const good = Color(0xFF15803D);
  static const warn = Color(0xFFD97706);
  static const bad = Color(0xFFDC2626);

  /// Colour for a 0-100 score.
  static Color forScore(num score) => score >= 85
      ? good
      : score >= 70
      ? const Color(0xFF4D7C0F)
      : score >= 50
      ? warn
      : bad;

  static Color forSeverity(String s) => switch (s) {
    'high' => bad,
    'medium' => warn,
    _ => textMuted,
  };
}

/// Spacing and corner sizes used everywhere.
class AppSizes {
  static const radius = 12.0;
  static const radiusLarge = 16.0;
}

ThemeData buildTheme() {
  const scheme = ColorScheme.light(
    primary: AppColors.brand,
    onPrimary: Colors.white,
    primaryContainer: AppColors.brandTint,
    onPrimaryContainer: AppColors.brand,
    secondary: AppColors.brandLight,
    onSecondary: Colors.white,
    secondaryContainer: AppColors.brandTint,
    onSecondaryContainer: AppColors.brand,
    tertiary: AppColors.brandSoft,
    onTertiary: Colors.white,
    tertiaryContainer: AppColors.brandTint,
    onTertiaryContainer: AppColors.brand,
    error: AppColors.bad,
    onError: Colors.white,
    surface: Colors.white,
    onSurface: AppColors.text,
    onSurfaceVariant: AppColors.textMuted,
    surfaceContainerLowest: Colors.white,
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
    iconTheme: const IconThemeData(color: AppColors.brandSoft),
    dividerTheme: const DividerThemeData(color: AppColors.border, thickness: 1, space: 1),
    appBarTheme: AppBarTheme(
      backgroundColor: AppColors.brand,
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
      color: Colors.white,
      margin: const EdgeInsets.symmetric(vertical: 6),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppSizes.radiusLarge),
        side: const BorderSide(color: AppColors.border),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: AppColors.brand,
        foregroundColor: Colors.white,
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
        foregroundColor: Colors.white,
        elevation: 0,
        padding: buttonPadding,
        shape: rounded,
        textStyle: buttonText,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.brand,
        side: const BorderSide(color: AppColors.borderStrong),
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
      fillColor: Colors.white,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      labelStyle: const TextStyle(color: AppColors.textMuted),
      floatingLabelStyle: const TextStyle(color: AppColors.brand, fontWeight: FontWeight.w600),
      hintStyle: const TextStyle(color: AppColors.textFaint),
      prefixIconColor: WidgetStateColor.resolveWith(
        (s) => s.contains(WidgetState.focused) ? AppColors.brand : AppColors.textFaint,
      ),
      suffixIconColor: AppColors.textFaint,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppSizes.radius),
        borderSide: const BorderSide(color: AppColors.borderStrong),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppSizes.radius),
        borderSide: const BorderSide(color: AppColors.borderStrong),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppSizes.radius),
        borderSide: const BorderSide(color: AppColors.brand, width: 2),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppSizes.radius),
        borderSide: const BorderSide(color: AppColors.bad),
      ),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: Colors.white,
      selectedColor: AppColors.brand,
      secondarySelectedColor: AppColors.brand,
      checkmarkColor: Colors.white,
      labelStyle: text.labelLarge?.copyWith(color: AppColors.text),
      secondaryLabelStyle: text.labelLarge?.copyWith(color: Colors.white),
      side: const BorderSide(color: AppColors.border),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      iconTheme: const IconThemeData(color: AppColors.brandSoft, size: 18),
    ),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: ButtonStyle(
        backgroundColor: WidgetStateColor.resolveWith(
          (s) => s.contains(WidgetState.selected) ? AppColors.brand : Colors.white,
        ),
        foregroundColor: WidgetStateColor.resolveWith(
          (s) => s.contains(WidgetState.selected) ? Colors.white : AppColors.brand,
        ),
        iconColor: WidgetStateColor.resolveWith(
          (s) => s.contains(WidgetState.selected) ? Colors.white : AppColors.brand,
        ),
        side: const WidgetStatePropertyAll(BorderSide(color: AppColors.borderStrong)),
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: Colors.white,
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
      backgroundColor: Colors.white,
      indicatorColor: AppColors.brandTint,
      selectedIconTheme: const IconThemeData(color: AppColors.brand),
      unselectedIconTheme: const IconThemeData(color: AppColors.textFaint),
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
    listTileTheme: const ListTileThemeData(iconColor: AppColors.brandSoft, textColor: AppColors.text),
    expansionTileTheme: const ExpansionTileThemeData(
      iconColor: AppColors.brand,
      collapsedIconColor: AppColors.brandSoft,
      textColor: AppColors.brand,
      collapsedTextColor: AppColors.text,
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: AppColors.brand,
      linearTrackColor: AppColors.brandTint,
      circularTrackColor: Colors.transparent,
    ),
    checkboxTheme: CheckboxThemeData(
      fillColor: WidgetStateColor.resolveWith((s) => s.contains(WidgetState.selected) ? AppColors.brand : Colors.white),
      side: const BorderSide(color: AppColors.borderStrong, width: 1.5),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
    ),
    switchTheme: SwitchThemeData(
      thumbColor: const WidgetStatePropertyAll(Colors.white),
      trackColor: WidgetStateColor.resolveWith(
        (s) => s.contains(WidgetState.selected) ? AppColors.brand : AppColors.border,
      ),
      trackOutlineColor: const WidgetStatePropertyAll(Colors.transparent),
    ),
    sliderTheme: const SliderThemeData(activeTrackColor: AppColors.brand, thumbColor: AppColors.brand),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: AppColors.brand,
      contentTextStyle: text.bodyMedium?.copyWith(color: Colors.white),
      behavior: SnackBarBehavior.floating,
      shape: rounded,
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: Colors.white,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      titleTextStyle: text.titleLarge?.copyWith(fontWeight: FontWeight.w700),
      iconColor: AppColors.brand,
    ),
    popupMenuTheme: PopupMenuThemeData(
      color: Colors.white,
      surfaceTintColor: Colors.transparent,
      elevation: 8,
      shadowColor: AppColors.brand.withValues(alpha: 0.15),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppSizes.radiusLarge)),
    ),
    tooltipTheme: TooltipThemeData(
      decoration: BoxDecoration(color: AppColors.brand, borderRadius: BorderRadius.circular(8)),
      textStyle: const TextStyle(color: Colors.white, fontSize: 12),
    ),
    badgeTheme: const BadgeThemeData(backgroundColor: AppColors.brand),
  );
}
