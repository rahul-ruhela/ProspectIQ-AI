import Companies from './Companies'

/** The qualified slice of Companies — what a salesperson should actually work. */
export default function Prospects() {
  return (
    <Companies
      qualifiedOnly
      title="Prospects"
      subtitle="Companies that cleared the quality gate and scored 60 or above. These are worth a human conversation."
    />
  )
}
