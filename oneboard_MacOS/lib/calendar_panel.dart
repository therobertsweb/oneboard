import 'package:flutter/material.dart';

String calendarDate(DateTime date) => date.toIso8601String().substring(0, 10);

bool eventOnDate(Map event, DateTime day) {
  final date = calendarDate(day);
  final start = event['starts_on']?.toString() ?? '';
  final end = event['ends_on']?.toString() ?? '';
  return start.isNotEmpty &&
      date.compareTo(start) >= 0 &&
      date.compareTo(end.isEmpty ? start : end) <= 0;
}

class CalendarPanel extends StatefulWidget {
  const CalendarPanel({
    super.key,
    required this.events,
    required this.onCreate,
    required this.recordBuilder,
    this.now,
    this.busy = false,
  });
  final List<Map<String, dynamic>> events;
  final ValueChanged<String> onCreate;
  final Widget Function(Map<String, dynamic>) recordBuilder;
  final DateTime? now;
  final bool busy;

  @override
  State<CalendarPanel> createState() => _CalendarPanelState();
}

class _CalendarPanelState extends State<CalendarPanel> {
  late DateTime selected;
  late DateTime month;
  bool showAll = false;

  @override
  void initState() {
    super.initState();
    final today = widget.now ?? DateTime.now();
    selected = DateTime(today.year, today.month, today.day);
    month = DateTime(today.year, today.month);
  }

  void move(int delta) => setState(() {
    month = DateTime(month.year, month.month + delta);
    selected = month;
  });

  @override
  Widget build(BuildContext context) {
    final first = month.subtract(Duration(days: month.weekday - 1));
    final events =
        widget.events.where((e) => showAll || eventOnDate(e, selected)).toList()
          ..sort((a, b) => '${a['starts_on']}'.compareTo('${b['starts_on']}'));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            IconButton(
              tooltip: 'Previous month',
              onPressed: () => move(-1),
              icon: const Icon(Icons.chevron_left),
            ),
            Text(
              '${month.year}-${month.month.toString().padLeft(2, '0')}',
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
            ),
            IconButton(
              tooltip: 'Next month',
              onPressed: () => move(1),
              icon: const Icon(Icons.chevron_right),
            ),
            TextButton(
              onPressed: () => setState(() {
                final now = widget.now ?? DateTime.now();
                selected = DateTime(now.year, now.month, now.day);
                month = DateTime(now.year, now.month);
              }),
              child: const Text('Today'),
            ),
            const Spacer(),
            FilledButton.icon(
              onPressed: widget.busy
                  ? null
                  : () => widget.onCreate(calendarDate(selected)),
              icon: const Icon(Icons.add),
              label: const Text('Create event'),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            for (final day in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'])
              Expanded(child: Center(child: Text(day))),
          ],
        ),
        const SizedBox(height: 8),
        for (var week = 0; week < 6; week++)
          Row(
            children: [
              for (var weekday = 0; weekday < 7; weekday++)
                Expanded(
                  child: _day(first.add(Duration(days: week * 7 + weekday))),
                ),
            ],
          ),
        const SizedBox(height: 16),
        Row(
          children: [
            Expanded(
              child: Text(
                showAll ? 'All events' : 'Events · ${calendarDate(selected)}',
                style: const TextStyle(
                  fontSize: 17,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            FilterChip(
              label: const Text('Show all'),
              selected: showAll,
              onSelected: (value) => setState(() => showAll = value),
            ),
          ],
        ),
        const SizedBox(height: 12),
        if (events.isEmpty) const Text('No events for this selection.'),
        for (final event in events) widget.recordBuilder(event),
      ],
    );
  }

  Widget _day(DateTime day) {
    final count = widget.events.where((e) => eventOnDate(e, day)).length;
    final active = day == selected;
    return Padding(
      padding: const EdgeInsets.all(2),
      child: Material(
        color: active ? const Color(0xFFE1EFFF) : Colors.white,
        borderRadius: BorderRadius.circular(8),
        child: InkWell(
          borderRadius: BorderRadius.circular(8),
          onTap: () => setState(() {
            selected = day;
            showAll = false;
          }),
          child: Semantics(
            label: '${calendarDate(day)}, $count events',
            selected: active,
            child: SizedBox(
              height: 66,
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(
                    '${day.day}',
                    style: TextStyle(
                      fontWeight: active ? FontWeight.bold : FontWeight.normal,
                      color: day.month == month.month
                          ? Colors.black87
                          : Colors.grey,
                    ),
                  ),
                  if (count > 0)
                    Text(
                      '$count events',
                      style: const TextStyle(
                        fontSize: 10,
                        color: Color(0xFF007AFF),
                      ),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
