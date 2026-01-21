import {
  SubfinderScan,
  HTTPXScan,
  GAUScan,
  WaymoreScan,
  KatanaScan,
  PlaywrightScan,
  LinkFinderScan,
  MantraScan,
  FFUFScan,
  DNSxScan,
  SubjackScan,
  ASNMapScan,
  MapCIDRScan,
  NaabuScan,
} from '../forms'

const FORM_REGISTRY = {
  Subfinder: SubfinderScan,
  HTTPX: HTTPXScan,
  GAU: GAUScan,
  Waymore: WaymoreScan,
  Katana: KatanaScan,
  Playwright: PlaywrightScan,
  LinkFinder: LinkFinderScan,
  Mantra: MantraScan,
  FFUF: FFUFScan,
  DNSx: DNSxScan,
  Subjack: SubjackScan,
  ASNMap: ASNMapScan,
  MapCIDR: MapCIDRScan,
  Naabu: NaabuScan,
}

export default function ScanFormFactory({ type, ...props }) {
  const FormComponent = FORM_REGISTRY[type]

  if (!FormComponent) {
    return (
      <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-700">
        Unknown scan form: <b>{type}</b>
      </div>
    )
  }

  return <FormComponent {...props} />
}
