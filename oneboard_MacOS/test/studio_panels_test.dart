import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:oneboard_flutter/feature_catalog.dart';
import 'package:oneboard_flutter/preview_panel.dart';
import 'package:oneboard_flutter/studio_file_view.dart';
import 'package:oneboard_flutter/studio_terminal_view.dart';

void main() {
  test('preview follows the actual workspace page and rejects other origins', () {
    final base = Uri.parse('https://oneboard.example');
    expect(
      previewPathFromUri(
        base,
        'https://oneboard.example/site-manager/preview/pages/about%20us.html?picker=1',
      ),
      'pages/about us.html',
    );
    expect(
      previewPathFromUri(
        base,
        'https://elsewhere.example/site-manager/preview/index.html',
      ),
      isNull,
    );
    expect(previewPathFromUri(base, 'https://oneboard.example/login'), isNull);
    expect(previewPathFromUri(base, 'about:blank'), isNull);
    expect(
      previewPathFromUri(base, '/site-manager/preview/index.html'),
      isNull,
    );
  });

  group('coerceFieldValue', () {
    test('integer parses and clamps to min/max', () {
      const spec = FieldSpec(
        'threshold_days',
        FieldType.integer,
        min: 1,
        max: 365,
      );
      expect(coerceFieldValue(spec, 14, '42'), 42);
      expect(coerceFieldValue(spec, 14, '0'), 1);
      expect(coerceFieldValue(spec, 14, '9999'), 365);
    });

    test('integer rejects non-numeric text', () {
      const spec = FieldSpec('backup_id', FieldType.integer, min: 1);
      expect(
        () => coerceFieldValue(spec, 1, 'abc'),
        throwsA(isA<FormatException>()),
      );
    });

    test('boolean accepts true/false text', () {
      const spec = FieldSpec('draft', FieldType.boolean);
      expect(coerceFieldValue(spec, true, 'false'), false);
      expect(coerceFieldValue(spec, false, 'True'), true);
      expect(coerceFieldValue(spec, false, 'yes'), false);
    });

    test('dropdown only accepts listed options', () {
      const spec = FieldSpec(
        'status',
        FieldType.dropdown,
        options: ['open', 'done'],
      );
      expect(coerceFieldValue(spec, 'open', 'done'), 'done');
      expect(
        () => coerceFieldValue(spec, 'open', 'archived'),
        throwsA(isA<FormatException>()),
      );
    });

    test('date requires YYYY-MM-DD', () {
      const spec = FieldSpec('starts_on', FieldType.date);
      expect(coerceFieldValue(spec, '', '2026-11-01'), '2026-11-01');
      expect(
        () => coerceFieldValue(spec, '', '11/01/2026'),
        throwsA(isA<FormatException>()),
      );
      expect(
        () => coerceFieldValue(spec, '', '2026-13-40'),
        throwsA(isA<FormatException>()),
      );
    });

    test('month requires YYYY-MM', () {
      const spec = FieldSpec('period', FieldType.month);
      expect(coerceFieldValue(spec, '', '2026-10'), '2026-10');
      expect(
        () => coerceFieldValue(spec, '', '2026-13'),
        throwsA(isA<FormatException>()),
      );
      expect(
        () => coerceFieldValue(spec, '', '2026-10-05'),
        throwsA(isA<FormatException>()),
      );
    });

    test('stringList accepts comma-separated and JSON input', () {
      const spec = FieldSpec('channel_ids', FieldType.stringList);
      expect(coerceFieldValue(spec, <String>[], 'abc123, def456'), [
        'abc123',
        'def456',
      ]);
      expect(coerceFieldValue(spec, <String>[], '["a", "b"]'), ['a', 'b']);
      expect(coerceFieldValue(spec, <String>[], '  '), <String>[]);
    });

    test('legacy fallback keeps bool/num/JSON/raw behavior', () {
      expect(coerceFieldValue(null, true, 'false'), false);
      expect(coerceFieldValue(null, 3, '7'), 7);
      expect(coerceFieldValue(null, <String>[], '{"a": 1}'), {'a': 1});
      expect(coerceFieldValue(null, 'x', 'plain'), 'plain');
      expect(
        () => coerceFieldValue(null, <String>[], '{oops'),
        throwsA(isA<FormatException>()),
      );
    });

    test('calendar and remote templates use valid backend values', () {
      final calendar = featurePages
          .firstWhere((page) => page.title == 'Calendar')
          .actions
          .firstWhere((action) => action.label == 'Create event');
      expect(calendar.body, contains('"kind": "promo"'));
      expect(calendar.body, isNot(contains('"kind": "promotion"')));
      final remote = featurePages
          .firstWhere((page) => page.title == 'Studio')
          .actions
          .firstWhere((action) => action.label == 'Save remote connection');
      expect(remote.body, contains('"key"'));
      expect(remote.body, isNot(contains('ssh_key')));
    });

    test('folder and file values pass through trimmed', () {
      const folder = FieldSpec('path', FieldType.folder);
      const file = FieldSpec('key_path', FieldType.file);
      expect(coerceFieldValue(folder, '', '  /tmp/site  '), '/tmp/site');
      expect(coerceFieldValue(file, '', '/tmp/key.pem'), '/tmp/key.pem');
    });

    test('directory inputs never use free-text fields', () {
      final remote = featurePages
          .firstWhere((page) => page.title == 'Studio')
          .actions
          .firstWhere((action) => action.label == 'Save remote connection');
      expect(remote.specFor('key_path')?.type, FieldType.file);
      expect(remote.specFor('host')?.type, FieldType.text);
    });

    test('the app only offers Muse as AI provider', () {
      final settings = featurePages.firstWhere(
        (page) => page.title == 'Settings',
      );
      final labels = settings.actions.map((action) => action.label).toList();
      expect(labels, contains('Save Muse credentials'));
      expect(labels, contains('Save Muse model'));
      expect(
        labels.any((label) => label.contains('anthropic')),
        isFalse,
      );
      expect(
        labels.any((label) => label.contains('openrouter')),
        isFalse,
      );
      expect(labels, isNot(contains('View AI providers')));
      expect(labels, isNot(contains('Save default provider')));
      final policy = settings.actions.firstWhere(
        (action) => action.label == 'Save Muse model',
      );
      expect(policy.specFor('provider'), isNull);
      expect(policy.specFor('model')?.type, FieldType.text);
    });
  });

  group('terminalOf', () {
    test('extracts terminal blocks and ignores other results', () {
      expect(
        terminalOf({
          'ok': true,
          'terminal': {'command': 'ls', 'exit_code': 0, 'output': 'ok'},
        }),
        isA<Map<String, dynamic>>(),
      );
      expect(terminalOf({'ok': true, 'manager': {}}), isNull);
      expect(terminalOf({'ok': true, 'terminal': 'ran'}), isNull);
      expect(terminalOf({'ok': true, 'terminal': {}}), isNull);
    });

    test('resultStatusLabel reflects ok flag', () {
      expect(resultStatusLabel({'ok': true}), 'Done');
      expect(resultStatusLabel({'ok': false}), 'Needs attention');
      expect(resultStatusLabel({}), 'Done');
    });
  });

  group('preview helpers', () {
    test('previewFileUri defaults to index.html and encodes segments', () {
      final base = Uri.parse('http://127.0.0.1:51249');
      expect(
        previewFileUri(base, '').toString(),
        'http://127.0.0.1:51249/site-manager/preview/index.html',
      );
      expect(
        previewFileUri(base, '/blog/my post.html').toString(),
        'http://127.0.0.1:51249/site-manager/preview/blog/my%20post.html',
      );
    });

    test('preview devices match web sizes plus tablet', () {
      expect(PreviewDevice.desktop.maxWidth, isNull);
      expect(PreviewDevice.tablet.maxWidth, 768);
      expect(PreviewDevice.mobile.maxWidth, 390);
    });

    test('previewSelectionPayload carries the workspace path', () {
      final payload = previewSelectionPayload({
        'page': 'index.html',
        'selector': 'h1',
      }, '/tmp/site');
      expect(payload['selector'], 'h1');
      expect(payload['expected_directory_path'], '/tmp/site');
      expect(
        previewSelectionPayload({'selector': 'h1'}, ''),
        isNot(contains('expected_directory_path')),
      );
    });

    test('selectionLabel truncates long text', () {
      expect(selectionLabel({'selector': 'h1'}), 'h1');
      expect(selectionLabel({'selector': 'h1', 'text': 'Hello'}), 'h1 — Hello');
      final long = selectionLabel({'selector': 'p', 'text': 'x' * 200});
      expect(long.length, 'p — '.length + 80);
    });
  });

  group('isHtmlFile', () {
    test('matches html extensions case-insensitively', () {
      expect(isHtmlFile('index.html'), isTrue);
      expect(isHtmlFile('page.HTM'), isTrue);
      expect(isHtmlFile('style.css'), isFalse);
      expect(isHtmlFile('photo.png'), isFalse);
    });
  });

  group('studio labels', () {
    test('quickPromptLabel covers backend keys with fallback', () {
      expect(quickPromptLabel('hero'), 'Document workspace');
      expect(quickPromptLabel('section'), 'Suggest new file');
      expect(quickPromptLabel('cta'), 'Review & fix');
      expect(quickPromptLabel('landing'), 'Draft document');
      expect(quickPromptLabel('my_prompt'), 'my prompt');
    });

    test('teamShareLabel summarizes team, role, and view-only', () {
      expect(
        teamShareLabel({
          'team': {'name': 'Acme'},
          'role': 'editor',
          'permissions': {'edit': true},
        }),
        'Shared by Acme · editor',
      );
      expect(
        teamShareLabel({
          'team': {'name': 'Acme'},
          'role': 'viewer',
          'permissions': {'edit': false},
        }),
        'Shared by Acme · viewer · view only',
      );
      expect(teamShareLabel({}), 'Shared by Team');
    });
  });

  testWidgets('TerminalResultView shows exit badge, command, and output', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: TerminalResultView(
            terminal: {
              'command': 'npm run build',
              'cwd': '/tmp/site',
              'exit_code': 0,
              'output': 'built in 3s',
              'started_at': '2026-10-29',
            },
          ),
        ),
      ),
    );
    expect(find.text('Exit 0'), findsOneWidget);
    expect(find.textContaining('npm run build'), findsOneWidget);
    expect(find.textContaining('built in 3s'), findsOneWidget);
  });

  testWidgets('TerminalResultView flags failing exit codes', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: TerminalResultView(
            terminal: {'command': 'false', 'exit_code': 1, 'output': ''},
          ),
        ),
      ),
    );
    expect(find.text('Exit 1'), findsOneWidget);
    expect(find.text('The command produced no output.'), findsOneWidget);
  });

  testWidgets('ActionResultCard surfaces highlights and terminal', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ActionResultCard(
            result: const {
              'ok': true,
              'summary': 'Backup created.',
              'terminal': {'command': 'ls', 'exit_code': 0, 'output': 'a'},
            },
            detailsBuilder: (value) => Text('$value'),
          ),
        ),
      ),
    );
    expect(find.text('Done'), findsOneWidget);
    expect(find.text('Backup created.'), findsOneWidget);
    expect(find.text('Exit 0'), findsOneWidget);
    expect(find.text('Details'), findsOneWidget);
  });
}
