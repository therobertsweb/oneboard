import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:oneboard_flutter/buffer_composer.dart';
import 'package:oneboard_flutter/feature_catalog.dart';
import 'package:oneboard_flutter/health_panel.dart';
import 'package:oneboard_flutter/request_thread_view.dart';
import 'package:oneboard_flutter/settings_panel.dart';
import 'package:oneboard_flutter/site_brand_panel.dart';
import 'package:oneboard_flutter/studio_terminal_view.dart';
import 'package:oneboard_flutter/teams_panel.dart';

void main() {
  group('buffer helpers', () {
    test('channelLabel combines name, service, and organization', () {
      expect(
        channelLabel({
          'id': 'c1',
          'name': 'Acme IG',
          'service': 'instagram',
          'organization_name': 'Acme',
        }),
        'Acme IG (instagram · Acme)',
      );
      expect(channelLabel({'id': 'c2'}), 'c2');
      expect(channelLabel({}), 'Channel');
    });

    test('bufferPostPayload trims text and omits empty extras', () {
      final payload = bufferPostPayload(
        channelIds: ['c1'],
        text: '  Hello  ',
        postType: 'reel',
        draft: false,
        publishNow: true,
        imageUrl: 'https://example.com/a.png',
        workspacePath: '/tmp/site',
      );
      expect(payload['text'], 'Hello');
      expect(payload['post_type'], 'reel');
      expect(payload['draft'], false);
      expect(payload['publish_now'], true);
      expect(payload['image_url'], 'https://example.com/a.png');
      expect(payload['expected_directory_path'], '/tmp/site');
      final minimal = bufferPostPayload(channelIds: ['c1'], text: 'Hi');
      expect(minimal['draft'], true);
      expect(minimal, isNot(contains('image_url')));
      expect(minimal, isNot(contains('expected_directory_path')));
    });

    test('socialImageStateLabel distinguishes generated images', () {
      expect(
        socialImageStateLabel(hasImage: false, generated: false),
        'No image attached',
      );
      expect(
        socialImageStateLabel(hasImage: true, generated: false),
        'Image attached',
      );
      expect(
        socialImageStateLabel(hasImage: true, generated: true),
        'AI image attached',
      );
    });

    test('bufferDiagnosisTitle separates missing key from rejected key', () {
      expect(
        bufferDiagnosisTitle(keyConfigured: false),
        'Buffer is not connected',
      );
      expect(
        bufferDiagnosisTitle(keyConfigured: true),
        'Buffer rejected the saved key',
      );
      expect(
        bufferDiagnosisDetail(keyConfigured: false, backendError: 'No key.'),
        contains('locally'),
      );
      expect(
        bufferDiagnosisDetail(keyConfigured: true, backendError: 'Bad key.'),
        contains('Bad key.'),
      );
    });

    test('socialImageStateLabel pending shows preview only', () {
      expect(
        socialImageStateLabel(hasImage: true, generated: true, pending: true),
        'Preview only',
      );
      expect(
        socialImageStateLabel(hasImage: true, generated: true),
        'AI image attached',
      );
    });

    test('media notices keep the backend detail', () {
      expect(
        mediaPendingNotice('Exception: Set your media server.'),
        'Image saved to your library, but it cannot travel with the post yet. Set your media server.',
      );
      expect(
        mediaPublishBlockedNotice('Set your media server.'),
        contains('remove the image to publish text only'),
      );
    });

    test('socialImageEditPayload trims url and instruction', () {
      expect(
        socialImageEditPayload('  /uploads/a.png  ', '  Add sun  '),
        {'image_url': '/uploads/a.png', 'instruction': 'Add sun'},
      );
    });

    test('parseSuggestionItems drops entries without a prompt', () {
      final items = parseSuggestionItems([
        {'title': 'Launch', 'prompt': 'Announce the launch'},
        {'title': 'Empty'},
        'not-a-map',
      ]);
      expect(items, hasLength(1));
      expect(items.first['title'], 'Launch');
      expect(items.first['prompt'], 'Announce the launch');
      expect(parseSuggestionItems(null), isEmpty);
      expect(parseSuggestionItems({}), isEmpty);
    });
  });

  group('settings helpers', () {
    test('aiCredentialsPayload only sends filled keys', () {
      final payload = aiCredentialsPayload('secret', {
        'muse_api_key': '  key-1 ',
        'unused_key': '  ',
      });
      expect(payload, {
        'current_password': 'secret',
        'muse_api_key': 'key-1',
      });
    });

    test('looksLikeEmail validates basic addresses', () {
      expect(looksLikeEmail('a@b.com'), isTrue);
      expect(looksLikeEmail('  a@b.com  '), isTrue);
      expect(looksLikeEmail('nope'), isFalse);
      expect(looksLikeEmail('a@b'), isFalse);
      expect(looksLikeEmail(''), isFalse);
    });

    test('teams catalog covers revoke and accept-by-id', () {
      final teams = featurePages.firstWhere((page) => page.title == 'Teams');
      final paths = teams.actions.map((action) => action.path).toSet();
      expect(paths, contains('/api/teams/:team_id/invites/:invite_id'));
      expect(paths, contains('/api/teams/invites/:invite_id/accept'));
    });
  });

  group('health helpers', () {
    test('findingIsIgnored reads the status field', () {
      expect(findingIsIgnored({'status': 'ignored'}), isTrue);
      expect(findingIsIgnored({'status': 'open'}), isFalse);
      expect(findingIsIgnored({}), isFalse);
    });

    test('findingTitle humanizes check and page', () {
      expect(
        findingTitle({'check': 'missing_alt', 'page': 'index.html'}),
        'Missing alt · index.html',
      );
      expect(findingTitle({}), 'Issue');
    });

    test('findingProposalText prefers summary-like keys', () {
      expect(
        findingProposalText({
          'proposal': {'action': 'Add it', 'summary': 'First choice'},
        }),
        'First choice',
      );
      expect(findingProposalText({'proposal': {}}), '');
      expect(findingProposalText({}), '');
      expect(findingProposalText({'proposal': 'text'}), '');
    });

    test('findingSeverityColor distinguishes severities', () {
      expect(findingSeverityColor('critical'), const Color(0xFFB33142));
      expect(findingSeverityColor('warning'), const Color(0xFFB25E09));
      expect(findingSeverityColor('info'), isNot(const Color(0xFFB33142)));
    });
  });

  group('request helpers', () {
    test('requestTitle prefers client, page, text, message', () {
      expect(requestTitle({'client_name': 'Ana'}), 'Ana');
      expect(requestTitle({'page': 'index.html'}), 'index.html');
      expect(requestTitle({'id': 7}), 'Request 7');
      expect(requestTitle({'text': 'x' * 200}).length, 91);
    });

    test('requestStatusColor distinguishes states', () {
      expect(requestStatusColor('done'), const Color(0xFF1F9D55));
      expect(requestStatusColor('open'), const Color(0xFFB25E09));
    });
  });

  group('teams helpers', () {
    test('memberLabel combines name and email', () {
      expect(
        memberLabel({'name': 'Ana', 'email': 'a@b.com'}),
        'Ana (a@b.com)',
      );
      expect(memberLabel({'email': 'a@b.com'}), 'a@b.com');
      expect(memberLabel({'id': 3}), 'Member 3');
    });

    test('roleColor highlights privileged roles', () {
      expect(roleColor('owner'), const Color(0xFFB33142));
      expect(roleColor('viewer'), isNot(const Color(0xFFB33142)));
    });
  });

  group('site brand helpers', () {
    test('formatImageSize scales bytes', () {
      expect(formatImageSize(512), '512 B');
      expect(formatImageSize(2048), '2.0 KB');
      expect(formatImageSize(5 * 1024 * 1024), '5.0 MB');
    });

    test('brandFieldLabel title-cases keys', () {
      expect(brandFieldLabel('business_name'), 'Business Name');
      expect(brandFieldLabel('primary'), 'Primary');
    });

    test('brand field lists match the backend schema', () {
      expect(
        brandTextFields,
        containsAll([
          'business_name',
          'tagline',
          'services',
          'audience',
          'tone',
          'phone',
          'email',
          'address',
          'website',
          'notes',
        ]),
      );
      expect(brandColorFields, ['primary', 'secondary', 'accent']);
      expect(brandFontFields, ['headings', 'body']);
    });
  });

  group('findLinks', () {
    test('collects links from nested results without duplicates', () {
      final links = findLinks({
        'share_url': 'https://example.com/s/1',
        'nested': {
          'items': [
            'see https://example.com/s/1 and http://a.io/x',
            42,
          ],
        },
        'plain': 'no link here',
      });
      expect(links, ['https://example.com/s/1', 'http://a.io/x']);
    });

    test('returns empty when there are no links', () {
      expect(findLinks({'ok': true, 'count': 3}), isEmpty);
      expect(findLinks(null), isEmpty);
    });
  });

  testWidgets('HealthPanel shows findings with direct actions', (tester) async {
    FeatureAction? lastAction;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: HealthPanel(
            health: {
              'open_count': 1,
              'can_edit': true,
              'findings': [
                {
                  'id': 5,
                  'check': 'missing_alt',
                  'severity': 'warning',
                  'page': 'index.html',
                  'detail': 'Image without alt text.',
                  'status': 'open',
                  'proposal': {'summary': 'Add descriptive alt text.'},
                },
              ],
              'ignored': [
                {'id': 6, 'check': 'old', 'severity': 'info', 'status': 'ignored'},
              ],
            },
            actions: const [
              FeatureAction('Scan site', 'POST', '/api/site-manager/health/scan'),
              FeatureAction(
                'Apply fix',
                'POST',
                '/api/site-manager/health/findings/:finding_id/apply',
              ),
              FeatureAction(
                'Ignore finding',
                'POST',
                '/api/site-manager/health/findings/:finding_id/ignore',
              ),
              FeatureAction(
                'Reopen finding',
                'POST',
                '/api/site-manager/health/findings/:finding_id/reopen',
              ),
            ],
            busy: false,
            onRunAction: (action, {pathOverrides}) => lastAction = action,
          ),
        ),
      ),
    );
    expect(find.text('Open issues (1)'), findsOneWidget);
    expect(find.textContaining('Missing alt'), findsOneWidget);
    expect(find.text('Add descriptive alt text.'), findsOneWidget);
    expect(find.text('Ignored (1)'), findsOneWidget);
    await tester.tap(find.text('Apply fix').first);
    expect(lastAction?.label, 'Apply fix');
  });

  testWidgets('ActionResultCard shows embed code blocks', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ActionResultCard(
            result: const {
              'ok': true,
              'snippet': '<form action="https://x.test/s">',
            },
            detailsBuilder: (value) => Text('$value'),
          ),
        ),
      ),
    );
    expect(find.text('Embed code'), findsOneWidget);
    expect(find.textContaining('<form'), findsOneWidget);
  });

  testWidgets('ActionResultCard lists generated links with open buttons', (
    tester,
  ) async {
    String? opened;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ActionResultCard(
            result: const {
              'ok': true,
              'share_url': 'https://example.com/s/abc',
            },
            detailsBuilder: (value) => Text('$value'),
            onOpenLink: (url) => opened = url,
          ),
        ),
      ),
    );
    expect(find.text('Links'), findsOneWidget);
    expect(find.text('https://example.com/s/abc'), findsOneWidget);
    await tester.tap(find.text('Open'));
    expect(opened, 'https://example.com/s/abc');
  });
}
