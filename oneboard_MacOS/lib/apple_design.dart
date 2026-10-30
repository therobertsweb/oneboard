import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' show CupertinoIcons;

const boardBlue = Color(0xFF246BFD);
const boardInk = Color(0xFF151A28);
const boardMuted = Color(0xFF777E93);

class BoardMark extends StatelessWidget {
  const BoardMark({super.key, this.size = 44});
  final double size;
  @override
  Widget build(BuildContext context) => Container(
    width: size,
    height: size,
    decoration: BoxDecoration(
      gradient: const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [Color(0xFF202735), Color(0xFF080C14)],
      ),
      borderRadius: BorderRadius.circular(size * .26),
      boxShadow: const [
        BoxShadow(
          color: Color(0x180D162B),
          blurRadius: 18,
          offset: Offset(0, 6),
        ),
      ],
    ),
    padding: EdgeInsets.all(size * .21),
    child: CustomPaint(painter: _MarkPainter()),
  );
}

class _MarkPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = size.width * .21
      ..strokeCap = StrokeCap.round
      ..shader = const SweepGradient(
        colors: [
          Color(0xFF7670FF),
          Color(0xFF368BFF),
          Color(0xFF59BFFF),
          Color(0xFF5147E8),
          Color(0xFF7670FF),
        ],
      ).createShader(rect);
    canvas.drawArc(
      rect.deflate(size.width * .12),
      math.pi * .75,
      math.pi * 1.87,
      false,
      paint,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class BoardBackdrop extends StatelessWidget {
  const BoardBackdrop({super.key, required this.child});
  final Widget child;
  @override
  Widget build(BuildContext context) => DecoratedBox(
    decoration: const BoxDecoration(
      gradient: LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [Color(0xFFF9FAFE), Color(0xFFF0F2FB), Color(0xFFF5F2FC)],
      ),
    ),
    child: child,
  );
}

class BoardSurface extends StatelessWidget {
  const BoardSurface({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(24),
  });
  final Widget child;
  final EdgeInsetsGeometry padding;
  @override
  Widget build(BuildContext context) => Container(
    padding: padding,
    decoration: BoxDecoration(
      color: Colors.white.withValues(alpha: .86),
      borderRadius: BorderRadius.circular(20),
      border: Border.all(color: Colors.white.withValues(alpha: .95)),
      boxShadow: const [
        BoxShadow(
          color: Color(0x060F234A),
          blurRadius: 24,
          offset: Offset(0, 8),
        ),
      ],
    ),
    child: child,
  );
}

class BoardFeatureTile extends StatelessWidget {
  const BoardFeatureTile({
    super.key,
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.color,
    required this.onTap,
  });
  final String title, subtitle;
  final IconData icon;
  final Color color;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) => Material(
    color: Colors.white.withValues(alpha: .84),
    borderRadius: BorderRadius.circular(18),
    child: InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(18),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(9),
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: .1),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Icon(icon, color: color, size: 22),
                ),
                const Spacer(),
                const Icon(
                  CupertinoIcons.arrow_up_right,
                  color: boardMuted,
                  size: 16,
                ),
              ],
            ),
            const SizedBox(height: 18),
            Text(
              title,
              style: const TextStyle(
                color: boardInk,
                fontWeight: FontWeight.w600,
                fontSize: 15,
              ),
            ),
            const SizedBox(height: 5),
            Text(
              subtitle,
              style: const TextStyle(
                color: boardMuted,
                fontSize: 12,
                height: 1.5,
              ),
            ),
          ],
        ),
      ),
    ),
  );
}

class BoardInspiration extends StatelessWidget {
  const BoardInspiration({super.key, required this.onOpen});
  final VoidCallback onOpen;
  @override
  Widget build(BuildContext context) => Container(
    clipBehavior: Clip.antiAlias,
    decoration: BoxDecoration(
      borderRadius: BorderRadius.circular(22),
      gradient: const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [Color(0xFF18233D), Color(0xFF1E2850), Color(0xFF4C467D)],
      ),
    ),
    child: Stack(
      children: [
        Positioned(
          right: -75,
          top: -55,
          child: Container(
            width: 260,
            height: 260,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(
                color: Colors.white.withValues(alpha: .08),
                width: 45,
              ),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(
                CupertinoIcons.sparkles,
                color: Color(0xFFB5BDFF),
                size: 24,
              ),
              const SizedBox(height: 36),
              const Text(
                'Focus.\nCreate.\nMake it happen.',
                style: TextStyle(
                  fontSize: 30,
                  fontWeight: FontWeight.w600,
                  letterSpacing: -1,
                  color: Colors.white,
                  height: 1.18,
                ),
              ),
              const SizedBox(height: 16),
              const Text(
                'A little clarity.\nRoom for your next big idea.',
                style: TextStyle(
                  color: Color(0xFFBFC8DF),
                  height: 1.6,
                  fontSize: 13,
                ),
              ),
              const SizedBox(height: 28),
              TextButton(
                onPressed: onOpen,
                style: TextButton.styleFrom(
                  foregroundColor: Colors.white,
                  backgroundColor: Colors.white.withValues(alpha: .12),
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 13,
                  ),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Flexible(child: Text('Open Studio')),
                    SizedBox(width: 14),
                    Icon(CupertinoIcons.arrow_right, size: 16),
                  ],
                ),
              ),
            ],
          ),
        ),
      ],
    ),
  );
}

ThemeData get boardTheme => ThemeData(
  brightness: Brightness.light,
  scaffoldBackgroundColor: const Color(0xFFF5F5F7),
  colorScheme: ColorScheme.fromSeed(
    seedColor: boardBlue,
    primary: boardBlue,
    brightness: Brightness.light,
    surface: Colors.white,
  ),
  useMaterial3: true,
  fontFamily: '.AppleSystemUIFont',
  platform: TargetPlatform.macOS,
  splashFactory: NoSplash.splashFactory,
  textTheme: const TextTheme(
    bodyMedium: TextStyle(fontSize: 13, color: boardInk),
    bodyLarge: TextStyle(fontSize: 14, color: boardInk),
  ),
  dialogTheme: DialogThemeData(
    backgroundColor: Colors.white,
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(22)),
  ),
  dividerColor: const Color(0x1F3C3C43),
  filledButtonTheme: FilledButtonThemeData(
    style: FilledButton.styleFrom(
      backgroundColor: boardBlue,
      foregroundColor: Colors.white,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(9)),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 11),
    ),
  ),
  inputDecorationTheme: InputDecorationTheme(
    filled: true,
    fillColor: const Color(0xFFF5F5F7),
    border: OutlineInputBorder(
      borderRadius: BorderRadius.circular(9),
      borderSide: BorderSide.none,
    ),
    enabledBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(9),
      borderSide: BorderSide.none,
    ),
    focusedBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(9),
      borderSide: const BorderSide(color: boardBlue, width: 1.5),
    ),
  ),
);
