import 'package:flutter/material.dart';
import 'package:oneboard_flutter/auth_link_dialog.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:oneboard_flutter/calendar_panel.dart';
import 'package:oneboard_flutter/feature_catalog.dart';
import 'package:oneboard_flutter/search_console_panel.dart';
import 'package:oneboard_flutter/search_palette.dart';

void main() {
  test(
    'email links are parsed locally and checked for the requested operation',
    () {
      expect(
        authLinkToken(
          'http://127.0.0.1:51249/verify-email/abc_123',
          reset: false,
        ),
        'abc_123',
      );
      expect(
        authLinkToken(
          'https://example.com/reset-password/abc-123',
          reset: true,
        ),
        'abc-123',
      );
      expect(authLinkToken('abc_123', reset: false), 'abc_123');
      expect(
        () => authLinkToken(
          'https://example.com/reset-password/abc',
          reset: false,
        ),
        throwsFormatException,
      );
      expect(
        () => authLinkToken('file:///verify-email/abc', reset: false),
        throwsFormatException,
      );
      expect(() => authLinkToken('', reset: true), throwsFormatException);
    },
  );
  FeatureAction action(String label) =>
      featurePages.expand((p) => p.actions).firstWhere((a) => a.label == label);
  test(
    'editing calendar preserves all editable fields without copying metadata',
    () {
      final record = {
        'id': 22,
        'title': 'Sale',
        'kind': 'promo',
        'brief': 'Details',
        'page': 'sale.html',
        'starts_on': '2030-04-10',
        'ends_on': '',
        'status': 'scheduled',
      };
      final payload = actionInitialValues(
        action('Update event'),
        record: record,
      );
      expect(
        payload,
        {...record}
          ..remove('id')
          ..remove('status'),
      );
      expect(
        coerceFieldValue(action('Update event').specFor('ends_on'), '', ''),
        '',
      );
      expect(
        () => coerceFieldValue(
          action('Update event').specFor('starts_on'),
          '',
          '',
        ),
        throwsFormatException,
      );
    },
  );
  test(
    'new dates are current and selected calendar day overrides the default',
    () {
      expect(
        actionInitialValues(
          action('Create event'),
          now: DateTime(2031, 2, 3),
        )['starts_on'],
        '2031-02-03',
      );
      expect(
        actionInitialValues(
          action('Create event'),
          record: {'starts_on': '2032-01-01'},
        )['starts_on'],
        '2032-01-01',
      );
      expect(
        actionInitialValues(
          action('Create shareable report'),
          now: DateTime(2031, 2, 3),
        )['period'],
        '2031-02',
      );
    },
  );
  test('panel-covered actions are hidden from the generic list exactly once', () {
    Set<String> covered(String title) => featurePages
        .firstWhere((page) => page.title == title)
        .actions
        .where((action) => action.coveredByPanel)
        .map((action) => action.label)
        .toSet();
    expect(
      covered('Settings'),
      {
        'Save account and company',
        'Connect Buffer',
        'Save Muse credentials',
        'Save Muse model',
        'Google diagnostics',
      },
    );
    expect(
      covered('Site & Brand'),
      {
        'Connect Search Console',
        'Select Google property',
        'Disconnect Search Console',
      },
    );
    expect(
      covered('Social'),
      {
        'View connected channels',
        'View post ideas',
        'Generate ideas with AI',
        'Write post',
        'View history',
        'Create draft or publish',
        'Edit image with AI',
        'Upload social image',
      },
    );
    // Everywhere else the generic buttons stay visible.
    for (final title in ['Site Health', 'Calendar', 'Requests']) {
      expect(covered(title), isEmpty, reason: title);
    }
  });
  test('search palette covers every section and catalog action', () {
    final entries = allPaletteEntries();
    final sections = entries.where((e) => e.kind == 'section').toList();
    expect(sections.map((e) => e.section).toSet(), hasLength(14));
    final actions = entries.where((e) => e.kind == 'action').toList();
    expect(
      actions.length,
      featurePages.fold<int>(0, (sum, page) => sum + page.actions.length),
    );
    expect(searchPaletteEntries(''), hasLength(9));
    expect(
      searchPaletteEntries('').every((e) => e.kind == 'section'),
      isTrue,
    );
  });
  test('search palette ranks title matches first', () {
    final results = searchPaletteEntries('social');
    expect(results.first.title, 'Social');
    expect(results.first.kind, 'section');
    expect(
      results.any((e) => e.kind == 'action' && e.subtitle == 'Social'),
      isTrue,
    );
    final buffer = searchPaletteEntries('buffer');
    expect(buffer, isNotEmpty);
    expect(buffer.first.title.toLowerCase(), contains('buffer'));
  });
  testWidgets('search palette picks entries through callbacks', (tester) async {
    var pickedSection = -1;
    FeatureAction? pickedAction;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SearchPalette(
            onPickSection: (section) => pickedSection = section,
            onPickAction: (section, action) => pickedAction = action,
          ),
        ),
      ),
    );
    await tester.enterText(find.byType(TextField), 'connect buffer');
    await tester.pump();
    expect(find.text('Connect Buffer'), findsOneWidget);
    await tester.tap(find.text('Connect Buffer'));
    await tester.pump();
    expect(pickedAction?.label, 'Connect Buffer');
    expect(pickedSection, -1);
  });
  test('friendlySearchError hides endpoint URLs', () {
    expect(
      friendlySearchError(
        'redirect_uri_mismatch: http://127.0.0.1:51249/api/x is not registered',
      ),
      'redirect_uri_mismatch: the registered address is not registered',
    );
    expect(friendlySearchError('plain  error'), 'plain error');
  });
  test('monitor boolean comes from SQLite and metadata is excluded', () {
    expect(
      actionInitialValues(
        action('Update monitor'),
        record: {
          'name': 'Production',
          'enabled': 1,
          'threshold_days': 30,
          'id': 12,
        },
      ),
      {'name': 'Production', 'enabled': true, 'threshold_days': 30},
    );
  });
  test(
    'brand colors and fonts round-trip as fields without losing nested values',
    () {
      final record = {
        'display_name': 'Shop',
        'client_name': 'Client',
        'brand': {
          'business_name': 'Shop',
          'colors': {
            'primary': '#123456',
            'secondary': '',
            'accent': '#abcdef',
          },
          'fonts': {'headings': 'Inter', 'body': 'Georgia'},
          'address': 'Main Street',
          'logo': '/private/logo.png',
        },
      };
      final payload = actionInitialValues(
        action('Save site and brand details'),
        record: record,
      );
      final flat = flattenFormObject(payload['brand'] as Map);
      expect(flat['colors.primary'], '#123456');
      expect(flat['fonts.body'], 'Georgia');
      expect(flat.containsKey('logo'), false);
      flat['colors.accent'] = '#654321';
      final expanded = expandFormObject(flat);
      expect(expanded['colors']['accent'], '#654321');
      expect(expanded['fonts']['headings'], 'Inter');
      expect(expanded['address'], 'Main Street');
    },
  );
  test(
    'calendar ranges include both endpoints and undated end means one day',
    () {
      final event = {'starts_on': '2030-04-10', 'ends_on': '2030-04-12'};
      expect(eventOnDate(event, DateTime(2030, 4, 9)), false);
      expect(eventOnDate(event, DateTime(2030, 4, 10)), true);
      expect(eventOnDate(event, DateTime(2030, 4, 12)), true);
      expect(eventOnDate(event, DateTime(2030, 4, 13)), false);
      expect(
        eventOnDate({'starts_on': '2030-04-10'}, DateTime(2030, 4, 11)),
        false,
      );
    },
  );
  testWidgets('month navigation, all events and creation on selected day', (
    tester,
  ) async {
    String? created;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: CalendarPanel(
              now: DateTime(2030, 4, 10),
              events: const [
                {'title': 'April sale', 'starts_on': '2030-04-10'},
                {'title': 'May sale', 'starts_on': '2030-05-01'},
              ],
              onCreate: (date) => created = date,
              recordBuilder: (e) => Text(e['title'].toString()),
            ),
          ),
        ),
      ),
    );
    expect(find.text('April sale'), findsOneWidget);
    expect(find.text('May sale'), findsNothing);
    await tester.tap(find.byTooltip('Next month'));
    await tester.pump();
    expect(find.text('May sale'), findsOneWidget);
    await tester.tap(find.text('Create event'));
    expect(created, '2030-05-01');
    await tester.tap(find.text('Show all'));
    await tester.pump();
    expect(find.text('April sale'), findsOneWidget);
  });
}
