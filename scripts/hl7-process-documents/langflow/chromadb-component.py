from copy import deepcopy
from chromadb.config import Settings
from langchain_chroma import Chroma
from typing_extensions import override
import hashlib

from langflow.base.vectorstores.model import LCVectorStoreComponent, check_cached_vector_store
from langflow.base.vectorstores.utils import chroma_collection_to_data
from langflow.io import BoolInput, DropdownInput, HandleInput, IntInput, StrInput
from langflow.schema import Data, DataFrame


class SimpleSmartChromaComponent(LCVectorStoreComponent):
    """Simple test version of Smart Chroma with basic duplicate detection."""

    display_name: str = "Simple Smart Chroma"
    description: str = "Simple test version with basic smart updates"
    name = "SimpleSmartChroma"
    icon = "Chroma"

    inputs = [
        StrInput(name="collection_name", display_name="Collection Name", value="langflow"),
        StrInput(name="persist_directory", display_name="Persist Directory"),
        *LCVectorStoreComponent.inputs,
        HandleInput(name="embedding", display_name="Embedding", input_types=["Embeddings"]),
        BoolInput(name="smart_updates", display_name="Enable Smart Updates", value=True),
        BoolInput(name="cleanup_orphans", display_name="Cleanup Orphaned Documents", value=False),
        StrInput(name="source_identifier", display_name="Source Identifier", info="Identifier for this data source (e.g., 'confluence_HE')"),
        BoolInput(name="force_update", display_name="Force Full Update", value=False),
        BoolInput(name="allow_duplicates", display_name="Allow Duplicates", value=False, advanced=True),
        IntInput(name="limit", display_name="Limit", advanced=True, value=1000),
        IntInput(name="batch_size", display_name="Batch Size", advanced=True, value=20, info="Number of documents to process in each batch to avoid token limits"),
    ]

    def generate_content_hash(self, text: str) -> str:
        """Generate a hash of the document content for change detection"""
        return hashlib.md5(text.encode()).hexdigest()

    def should_update_document(self, new_doc: Data, existing_doc: Data) -> bool:
        """Determine if a document needs updating"""
        if self.force_update:
            return True
            
        # Check lastModified timestamp first
        new_metadata = getattr(new_doc, 'data', {}).get('metadata', {}) if hasattr(new_doc, 'data') else {}
        existing_metadata = getattr(existing_doc, 'data', {}).get('metadata', {}) if hasattr(existing_doc, 'data') else {}
        
        new_modified = new_metadata.get('lastModified', '')
        existing_modified = existing_metadata.get('lastModified', '')
        
        if new_modified and existing_modified:
            if new_modified != existing_modified:
                print(f"  📅 Timestamp changed: {existing_modified} → {new_modified}")
                return True
        
        # Check content hash as fallback
        new_hash = self.generate_content_hash(new_doc.text)
        existing_hash = existing_metadata.get('content_hash', '')
        
        if new_hash != existing_hash:
            print(f"  🔄 Content changed: {existing_hash[:8]}... → {new_hash[:8]}...")
            return True
            
        return False

    def cleanup_orphaned_documents(self, vector_store: "Chroma", current_doc_ids: set) -> int:
        """Remove documents that are no longer in the source"""
        if not self.cleanup_orphans or not self.source_identifier:
            return 0
            
        try:
            stored_data = chroma_collection_to_data(vector_store.get(limit=self.limit))
            orphaned_ids = []
            
            for doc in stored_data:
                doc_metadata = getattr(doc, 'data', {}).get('metadata', {}) if hasattr(doc, 'data') else {}
                if (doc_metadata.get('source_identifier') == self.source_identifier and 
                    doc.id not in current_doc_ids):
                    orphaned_ids.append(doc.id)
            
            if orphaned_ids:
                unique_orphaned_ids = list(set(orphaned_ids))
                vector_store.delete(ids=unique_orphaned_ids)
                print(f"🧹 Cleaned up {len(unique_orphaned_ids)} orphaned documents")
                return len(unique_orphaned_ids)
                
        except Exception as e:
            print(f"⚠️ Error during cleanup: {str(e)}")
            
        return 0

    def add_documents_in_batches(self, vector_store: "Chroma", lc_docs: list, doc_ids: list) -> int:
        """Add documents to vector store in batches to avoid token limits"""
        if not lc_docs:
            return 0
            
        batch_size = getattr(self, 'batch_size', 20)  # Default to 20 if not set
        total_added = 0
        
        print(f"💾 Adding {len(lc_docs)} documents in batches of {batch_size}")
        
        for i in range(0, len(lc_docs), batch_size):
            batch_docs = lc_docs[i:i + batch_size]
            batch_ids = doc_ids[i:i + batch_size]
            
            try:
                vector_store.add_documents(batch_docs, ids=batch_ids)
                total_added += len(batch_docs)
                print(f"✅ Added batch {i//batch_size + 1}: {len(batch_docs)} documents")
                
            except Exception as e:
                if "max_tokens_per_request" in str(e):
                    print(f"⚠️ Token limit exceeded in batch {i//batch_size + 1}, trying smaller batches...")
                    # Try with smaller batches
                    smaller_batch_size = max(1, batch_size // 2)
                    
                    for j in range(i, min(i + batch_size, len(lc_docs)), smaller_batch_size):
                        smaller_batch_docs = lc_docs[j:j + smaller_batch_size]
                        smaller_batch_ids = doc_ids[j:j + smaller_batch_size]
                        
                        try:
                            vector_store.add_documents(smaller_batch_docs, ids=smaller_batch_ids)
                            total_added += len(smaller_batch_docs)
                            print(f"✅ Added smaller batch: {len(smaller_batch_docs)} documents")
                            
                        except Exception as e2:
                            if "max_tokens_per_request" in str(e2):
                                # Try individual documents as last resort
                                print(f"⚠️ Still too large, trying individual documents...")
                                for k in range(len(smaller_batch_docs)):
                                    try:
                                        vector_store.add_documents([smaller_batch_docs[k]], ids=[smaller_batch_ids[k]])
                                        total_added += 1
                                        print(f"✅ Added individual document: {smaller_batch_ids[k]}")
                                    except Exception as e3:
                                        print(f"❌ Failed to add document {smaller_batch_ids[k]}: {str(e3)}")
                            else:
                                print(f"❌ Error in smaller batch: {str(e2)}")
                                raise e2
                else:
                    print(f"❌ Error in batch {i//batch_size + 1}: {str(e)}")
                    raise e
        
        return total_added

    @override
    @check_cached_vector_store
    def build_vector_store(self) -> Chroma:
        print(f"🚀 SIMPLE SMART CHROMA - BUILD START")
        
        try:
            from chromadb import Client
            from langchain_chroma import Chroma
        except ImportError as e:
            msg = "Could not import Chroma integration package."
            raise ImportError(msg) from e

        persist_directory = self.resolve_path(self.persist_directory) if self.persist_directory else None

        chroma = Chroma(
            persist_directory=persist_directory,
            embedding_function=self.embedding,
            collection_name=self.collection_name,
        )

        print(f"🎯 CALLING SIMPLE SMART ADD DOCUMENTS")
        self._add_documents_simple_smart(chroma)
        
        self.status = chroma_collection_to_data(chroma.get(limit=self.limit))
        print(f"🏁 SIMPLE SMART CHROMA - BUILD COMPLETE")
        return chroma

    def _add_documents_simple_smart(self, vector_store: "Chroma") -> None:
        print(f"🔧 EXECUTING ENHANCED SMART ADD DOCUMENTS")
        
        ingest_data = self.ingest_data
        if not ingest_data:
            print("❌ No ingest data")
            return

        ingest_data = self._prepare_ingest_data()
        print(f"📊 Prepared {len(ingest_data or [])} documents")

        if not self.smart_updates:
            print("⚡ Smart updates disabled - using batched method")
            documents = [doc.to_lc_document() for doc in ingest_data]
            doc_ids = [getattr(doc, 'id', f"auto_{i}") for i, doc in enumerate(ingest_data)]
            self.add_documents_in_batches(vector_store, documents, doc_ids)
            return

        # Enhanced smart update logic with change detection
        existing_docs = chroma_collection_to_data(vector_store.get(limit=self.limit))
        existing_by_id = {doc.id: doc for doc in existing_docs if doc.id}
        
        print(f"🔍 Found {len(existing_by_id)} existing documents")
        print(f"🔍 Sample existing IDs: {list(existing_by_id.keys())[:10]}")
        
        # Check for old vs new format
        old_format_count = sum(1 for doc_id in existing_by_id.keys() if '_chunk_' not in doc_id)
        new_format_count = sum(1 for doc_id in existing_by_id.keys() if '_chunk_' in doc_id)
        print(f"🔍 ID Formats - Old: {old_format_count}, New: {new_format_count}")
        
        # Track statistics
        stats = {'new': 0, 'updated': 0, 'skipped': 0, 'orphans_removed': 0}
        current_doc_ids = set()
        
        # Process each document with enhanced logic
        documents_to_add = []
        documents_to_update = []
        chunk_counter = {}  # Track chunks per base document ID
        
        for doc in ingest_data:
            # Ensure document has proper metadata with source tracking
            if not hasattr(doc, 'data') or not doc.data:
                doc.data = {}
            if 'metadata' not in doc.data:
                doc.data['metadata'] = {}
            
            # Add content hash and source identifier
            doc.data['metadata']['content_hash'] = self.generate_content_hash(doc.text)
            if self.source_identifier:
                doc.data['metadata']['source_identifier'] = self.source_identifier
            
            # Generate consistent document ID (handling chunks properly)
            base_id = getattr(doc, 'id', None)
            if not base_id:
                base_id = f"auto_{len(documents_to_add) + len(documents_to_update)}"
            
            # Create unique chunk IDs
            if base_id in chunk_counter:
                chunk_counter[base_id] += 1
                unique_id = f"{base_id}_chunk_{chunk_counter[base_id]}"
            else:
                chunk_counter[base_id] = 0
                unique_id = f"{base_id}_chunk_0"
            
            doc.id = unique_id
            current_doc_ids.add(unique_id)
            
            print(f"📄 Processing: {unique_id} (base: {base_id})")
            
            # Check for existing documents (could be stored with old or new ID format)
            possible_existing_ids = [unique_id, base_id, f"{base_id}_chunk_0"]
            existing_doc = None
            existing_id = None
            
            for check_id in possible_existing_ids:
                if check_id in existing_by_id:
                    existing_doc = existing_by_id[check_id]
                    existing_id = check_id
                    print(f"  ✅ Found existing: {existing_id}")
                    break
            
            if not existing_doc:
                print(f"  ❌ No existing document found for: {possible_existing_ids}")
            
            if existing_doc:
                if self.should_update_document(doc, existing_doc):
                    print(f"🔄 UPDATING: {unique_id} (was: {existing_id})")
                    # If ID format changed, we need to delete the old one
                    if existing_id != unique_id:
                        try:
                            vector_store.delete(ids=[existing_id])
                            print(f"🗑️ Deleted old format: {existing_id}")
                        except Exception as e:
                            print(f"⚠️ Error deleting old ID {existing_id}: {str(e)}")
                    documents_to_update.append(doc)
                    stats['updated'] += 1
                else:
                    print(f"⏭️ SKIPPING: {unique_id} (no changes, existing: {existing_id})")
                    stats['skipped'] += 1
            else:
                print(f"✅ ADDING: {unique_id} (new)")
                documents_to_add.append(doc)
                stats['new'] += 1

        # Process updates (delete old versions first)
        if documents_to_update:
            try:
                # Get unique IDs to avoid duplicate deletion errors
                update_ids = list(set([doc.id for doc in documents_to_update]))
                vector_store.delete(ids=update_ids)
                print(f"🗑️ Deleted {len(update_ids)} documents for update")
                documents_to_add.extend(documents_to_update)
            except Exception as e:
                print(f"⚠️ Error deleting for update: {str(e)}")
                documents_to_add.extend(documents_to_update)

        # Add all new and updated documents using batched approach
        if documents_to_add:
            print(f"💾 Preparing {len(documents_to_add)} documents for batched addition")
            lc_docs = []
            doc_ids = []
            
            for doc in documents_to_add:
                # Create LangChain document with flattened metadata
                lc_doc = doc.to_lc_document()
                lc_doc.metadata = doc.data.get('metadata', {})
                lc_docs.append(lc_doc)
                doc_ids.append(doc.id)
            
            # Ensure all IDs are unique before adding
            unique_doc_ids = []
            unique_lc_docs = []
            seen_ids = set()
            
            for i, doc_id in enumerate(doc_ids):
                if doc_id not in seen_ids:
                    seen_ids.add(doc_id)
                    unique_doc_ids.append(doc_id)
                    unique_lc_docs.append(lc_docs[i])
                else:
                    print(f"⚠️ Skipping duplicate ID in batch: {doc_id}")
            
            if unique_lc_docs:
                # Use the new batched method instead of adding all at once
                added_count = self.add_documents_in_batches(vector_store, unique_lc_docs, unique_doc_ids)
                print(f"✅ Successfully added {added_count} unique documents in batches")
            else:
                print("❌ No unique documents to add after deduplication")
        
        # Cleanup orphaned documents if enabled
        if self.cleanup_orphans:
            stats['orphans_removed'] = self.cleanup_orphaned_documents(vector_store, current_doc_ids)
        
        # Generate comprehensive report
        print(f"""
🎯 ENHANCED SMART UPDATE COMPLETE
═══════════════════════════════════════
Collection: {self.collection_name}
Source: {self.source_identifier or 'Unknown'}

PROCESSING STATISTICS:
├─ New Documents: {stats['new']}
├─ Updated Documents: {stats['updated']} 
├─ Skipped (No Changes): {stats['skipped']}
└─ Orphans Removed: {stats['orphans_removed']}

SETTINGS:
├─ Smart Updates: {'Enabled' if self.smart_updates else 'Disabled'}
├─ Cleanup Orphans: {'Enabled' if self.cleanup_orphans else 'Disabled'}
├─ Force Update: {'Yes' if self.force_update else 'No'}
├─ Batch Size: {getattr(self, 'batch_size', 20)}
└─ Source Identifier: {self.source_identifier or 'None'}
═══════════════════════════════════════""")
        
        print(f"🎉 ENHANCED SMART UPDATE COMPLETE")