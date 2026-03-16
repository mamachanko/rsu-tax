import type { VerificationCheck } from '../types';

interface Props {
  checks: VerificationCheck[];
}

export function VerificationPanel({ checks }: Props) {
  const allPass = checks.every((c) => c.status === 'pass');
  const hasFailures = checks.some((c) => c.status === 'fail');

  return (
    <div className={`rounded-lg border p-4 ${
      allPass ? 'bg-green-50 border-green-200' :
      hasFailures ? 'bg-red-50 border-red-200' :
      'bg-yellow-50 border-yellow-200'
    }`}>
      <h3 className="font-medium text-sm mb-3">
        {allPass ? 'All Verification Checks Passed' :
         hasFailures ? 'Some Verification Checks Failed' :
         'Verification Checks — Review Warnings'}
      </h3>
      <div className="space-y-2">
        {checks.map((check, i) => (
          <div key={i} className="flex items-start gap-2 text-xs">
            <span className="mt-0.5 flex-shrink-0">
              {check.status === 'pass' && <span className="text-green-600">&#10003;</span>}
              {check.status === 'warn' && <span className="text-yellow-600">&#9888;</span>}
              {check.status === 'fail' && <span className="text-red-600">&#10007;</span>}
            </span>
            <div>
              <span className="font-medium">{check.name}: </span>
              <span className="text-gray-600">{check.message}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
