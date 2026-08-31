import EntitySearch from './EntitySearch.jsx'
import './EntityPanel.css'

const RELATION_LABELS = {
  CALLED: 'Phone call',
  FINANCIAL_LINK: 'Financial link',
}

const LINK_TYPE_LABELS = {
  PHONE: 'Phone',
  ACCOUNT: 'Account',
  VEHICLE: 'Vehicle',
}

function AttributeRow({ label, value }) {
  if (!value) return null
  return (
    <div className="entity-attr-row">
      <span className="entity-attr-key">{label}</span>
      <span className="entity-attr-value">{value}</span>
    </div>
  )
}

function PersonDetails({ entity, onSelectEntity }) {
  const { attributes } = entity
  const connectedPeople = entity.connections.filter((item) => item.type === 'PERSON')
  const connectedAccounts = entity.connections.filter((item) => item.type === 'ACCOUNT')

  return (
    <>
      <div className="entity-header">
        <span className="entity-type-badge entity-type-person">Person</span>
        <h3 className="entity-name">{entity.displayName}</h3>
        <span className="entity-id">{entity.id}</span>
      </div>

      {entity.aliases.length > 0 && (
        <div className="entity-subsection">
          <span className="entity-subsection-label">Aliases</span>
          <p className="entity-aliases">{entity.aliases.join(', ')}</p>
        </div>
      )}

      <div className="entity-subsection">
        <span className="entity-subsection-label">Attributes</span>
        <div className="entity-attr-list">
          <AttributeRow label="Gender" value={attributes.gender} />
          <AttributeRow label="Age" value={attributes.age} />
          <AttributeRow label="Occupation" value={attributes.occupation} />
          <AttributeRow label="State" value={attributes.state} />
          <AttributeRow label="District" value={attributes.district} />
          <AttributeRow label="Address" value={attributes.address} />
        </div>
      </div>

      <div className="entity-subsection">
        <span className="entity-subsection-label">Known links</span>
        {entity.knownLinks.length === 0 && connectedAccounts.length === 0 ? (
          <p className="entity-empty-note">No known links on file.</p>
        ) : (
          <ul className="entity-link-list">
            {entity.knownLinks.map((link) => (
              <li key={link.id} className="entity-link-item entity-link-static">
                <span className="entity-link-type">{LINK_TYPE_LABELS[link.type] ?? link.type}</span>
                <span className="entity-link-label">{link.label}</span>
              </li>
            ))}
            {connectedAccounts.map((link) => (
              <li key={link.id}>
                <button
                  type="button"
                  className="entity-link-item entity-link-button"
                  onClick={() => onSelectEntity(link.id)}
                >
                  <span className="entity-link-type">Unknown account</span>
                  <span className="entity-link-label">{link.displayName}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="entity-subsection">
        <span className="entity-subsection-label">Connected people</span>
        {connectedPeople.length === 0 ? (
          <p className="entity-empty-note">No connected people in this cluster.</p>
        ) : (
          <ul className="entity-link-list">
            {connectedPeople.map((connection) => (
              <li key={connection.id}>
                <button
                  type="button"
                  className="entity-link-item entity-link-button"
                  onClick={() => onSelectEntity(connection.id)}
                >
                  <span className="entity-link-type">
                    {RELATION_LABELS[connection.relation] ?? connection.relation}
                  </span>
                  <span className="entity-link-label">{connection.displayName}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  )
}

function EntityPanel({ entity, entityLoading, entityError, onSelectEntity }) {
  return (
    <aside className="entity-panel">
      <div className="panel-block">
        <span className="panel-label">Entity search</span>
        <EntitySearch onSelectEntity={onSelectEntity} />
      </div>

      <div className="panel-block entity-details-block">
        <span className="panel-label">Entity details</span>
        {entityError ? (
          <div className="entity-details-empty">
            <p>Failed to load entity details: {entityError}</p>
          </div>
        ) : entityLoading ? (
          <div className="entity-details-empty">
            <p>Loading entity details…</p>
          </div>
        ) : entity ? (
          <div className="entity-details-content">
            <PersonDetails entity={entity} onSelectEntity={onSelectEntity} />
          </div>
        ) : (
          <div className="entity-details-empty">
            <p>
              Select an entity from the graph
              <br />
              to view its details.
            </p>
          </div>
        )}
      </div>
    </aside>
  )
}

export default EntityPanel
