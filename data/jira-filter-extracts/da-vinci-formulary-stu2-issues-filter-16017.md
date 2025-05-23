| Issue | Related URL | Resolution |
| --- | --- | --- |
| [FHIR-34283](https://jira.hl7.org/browse/FHIR-34283) | [https://build.fhir.org/ig/HL7/davinci-pdex-formulary/ValueSet-SemanticDrugVS.html#logical-definition-cld](https://build.fhir.org/ig/HL7/davinci-pdex-formulary/ValueSet-SemanticDrugVS.html#logical-definition-cld) | Retracted by submitter |
| [FHIR-34085](https://jira.hl7.org/browse/FHIR-34085) |  | Create ValueSet Sementic Drug Codes for RxNorm codes that are of Term Type (TTY) SCD, SBD, GPCK, and BPCK    Create ValueSet Sementic DrugForm Group for RxNorm codes that are of Term Type (TTY) SCDG and SBDG    slice MedicationKnowledge.code.coding, open pattern    - One slice cardinality 1..\* with binding to Semantic Drug Codes (required)    - One slice cardinality 0..\* with binding to Semantic Drug Form Group Codes (required)    Add requirement that servers shall support semantic drug form group code where semantic drug is of TTY SCD or SBD.    Add guidance on drug alternatives:  h4. Presenting Drug Alternatives    Finding appropriate alternatives of a prescribed medication is complex and often depends on additional clinical information about the patient well as the condition or set of conditions for which the medication is meant to address. The information and business rules necessary to identify possible therapeutic alternatives, and therefore the ability to search for such alternatives, lies outside of the scope of this guide. |
| [FHIR-33248](https://jira.hl7.org/browse/FHIR-33248) |  | Agree.  Will remove |
| [FHIR-33187](https://jira.hl7.org/browse/FHIR-33187) |  | Only need a link to more materials. Adding an endpoint creates more overhead than necessary for the requirement. Use InsurancePlan.contact with telecom.system = url instead.  |
| [FHIR-33186](https://jira.hl7.org/browse/FHIR-33186) |  | Create profile on Location that can be referenced from Payer InsurancePlan.coverageArea. Profile to include geolocation extension as Must Support along with name, description and address as Must Support.  |
| [FHIR-33185](https://jira.hl7.org/browse/FHIR-33185) |  | Add Payer Insurance Plan profile on InsurancePlan with an extension pointing the a Formulary profile on InsurancePlan in an extension under coverage.    Include cost sharing information for the formulary under plan.    Use the same codes as Da Vinci plan-net InsurancePlan.type. All other elements are compatible with Plan-net InsurancePlan, but cardinalities and Must Support are not the same across use cases. |
| [FHIR-33184](https://jira.hl7.org/browse/FHIR-33184) |  | Add MedicationKnowledge.doseForm in FormularyDrug profile as Must Support. Add dose-form as SHOULD search parameter. |
| [FHIR-33183](https://jira.hl7.org/browse/FHIR-33183) |  | Search parameters will be updated in support to the changes in the underlying structure of the IG.    [https://build.fhir.org/ig/HL7/davinci-pdex-formulary/search\_parameters.html]   h4. PayerInsurancePlan & Formulary (InsurancePlan)  \\|\\|Parameter\\|\\|Type\\|\\|Conf.\\|\\|Description\\|\\|Example\\|\\|  \\|[\_id\\|http://hl7.org/fhir/R4/search.html]\\|[token\\|https://www.hl7.org/fhir/search.html#token]\\|\*SHALL\*\\|FHIR resource id of an InsurancePlan\\|{{GET [base]/InsurancePlan?\_id=[id]}}\\|  \\|[\_lastUpdated\\|https://build.fhir.org/ig/HL7/davinci-pdex-formulary/SearchParameter-InsurancePlan-lastupdated.html]\\|[date\\|https://www.hl7.org/fhir/search.html#date]\\|\*SHALL\*\\|Accesses the last updated date of an InsurancePlan\\|{{GET [base]/InsurancePlan?\_lastUpdated=[date]}}\\|  \\|[identifier\\|https://build.fhir.org/ig/HL7/davinci-pdex-formulary/SearchParameter-InsurancePlan-identifier.html]\\|[token\\|https://www.hl7.org/fhir/search.html#token]\\|\*SHALL\*\\|Accesses the business identifier of an InsurancePlan\\|{{GET [base]/InsurancePlan?identifier=[system]\\\\|[code]}}\\|  \\|[status\\|https://build.fhir.org/ig/HL7/davinci-pdex-formulary/SearchParameter-InsurancePlan-status.html]\\|[token\\|https://www.hl7.org/fhir/search.html#token]\\|\*SHALL\*\\|Accesses the status of an InsurancePlan\\|{{GET [base]/InsurancePlan?status=[code]}}\\|  \\|[period\\|https://build.fhir.org/ig/HL7/davinci-pdex-formulary/SearchParameter-InsurancePlan-period.html]\\|[date\\|https://www.hl7.org/fhir/search.html#date]\\|\*SHALL\*\\|Accesses the active period of an InsurancePlan\\|{{GET [base]/InsurancePlan?period=[date]}}\\|  \\|[type\\|https://build.fhir.org/ig/HL7/davinci-pdex-formulary/SearchParameter-InsurancePlan-type.html]\\|[token\\|https://www.hl7.org/fhir/search.html#token]\\|\*SHALL\*\\|Accesses the Type of an InsurancePlan\\|{{GET [base]/InsurancePlan?type=[system]\\\\|[code]}}\\|  \\|[name\\|https://build.fhir.org/ig/HL7/davinci-pdex-formulary/SearchParameter-InsurancePlan-name.html]\\|[string\\|https://www.hl7.org/fhir/search.html#string]\\|\*SHALL\*\\|Accesses the name of an InsurancePlan\\|{{GET [base]/InsurancePlan?name=[string]}}\\|  \\|[coverage-type\\|https://build.fhir.org/ig/HL7/davinci-pdex-formulary/SearchParameter-InsurancePlan-coverage-type.html]\\|[token\\|https://www.hl7.org/fhir/search.html#token]\\|\*SHALL\*\\|Accesses the coverage type of an InsurancePlan\\|{{GET [base]/InsurancePlan?coverage-type=[system]\\\\|[code]}}\\|  \\|[formulary-coverage\\|https://build.fhir.org/ig/HL7/davinci-pdex-formulary/SearchParameter-InsurancePlan-formulary-coverage.html]\\|[reference\\|https://www.hl7.org/fhir/search.html#reference]\\|\*SHALL\*\\|Accesses the Coverage Formulary Reference of an InsurancePlan\\|{{GET [base]/InsurancePlan?formulary-coverage=[reference]}}\\|  \\|[coverage-area\\|https://build.fhir.org/ig/HL7/davinci-pdex-formulary/SearchParameter-InsurancePlan-coverage-area.html]\\|[reference\\|https://www.hl7.org/fhir/search.html#reference]\\|\*SHALL\*\\|Search InsurancePlan by coverage location.\\|{{GET [base]/InsurancePlan?coverage-area=[reference]}}\\|       h4. InsurancePlanLocation (Location)  \\|\\|Parameter\\|\\|Type\\|\\|Conf.\\|\\|Description\\|\\|Example\\|\\|  \\|[\_id\\|http://hl7.org/fhir/R4/search.html]\\|[token\\|https://www.hl7.org/fhir/search.html#token]\\|\*SHALL\*\\|FHIR resource id of a Location\\|{{GET [base]/Location?\_id=[id]}}\\|  \\|[\_lastUpdated\\|https://www.hl7.org/fhir/search.html#lastUpdated]\\|[date\\|https://www.hl7.org/fhir/search.html#date]\\|\*SHOULD\*\\|Access the last updated date of a Location\\|{{GET [base]/Location?\_lastUpdated=[date]}}\\|  \\|address\\|[string\\|https://www.hl7.org/fhir/search.html#string]\\|\*SHOULD\*\\|Access the address of a Location\\|{{GET [base]/Location?address=[string]}}\\|  \\|address-city\\|[string\\|https://www.hl7.org/fhir/search.html#string]\\|\*SHOULD\*\\|Access the city of a Location\\|{{GET [base]/Location?address-city=[string]}}\\|  \\|address-state\\|[string\\|https://www.hl7.org/fhir/search.html#string]\\|\*SHOULD\*\\|Access the state of a Location\\|{{GET [base]/Location?address-state=[string]}}\\|  \\|address-postalcode\\|[string\\|https://www.hl7.org/fhir/search.html#string]\\|\*SHOULD\*\\|Access the postal code of a Location\\|{{GET [base]/Location?address-postalcode=[string]}}\\|       h4. FormularyItem (Basic)  \\|\\|Parameter\\|\\|Type\\|\\|Conf.\\|\\|Description\\|\\|Example\\|\\|  \\|[\_id\\|http://hl7.org/fhir/R4/search.html]\\|[token\\|https://www.hl7.org/fhir/search.html#token]\\|\*SHALL\*\\|FHIR resource id of a FormularyItem\\|{{GET [base]/Basic?\_id=[id]}}\\|  \\|[\_lastUpdated\\|https://build.fhir.org/ig/HL7/davinci-pdex-formulary/SearchParameter-Basic-lastupdated.html]\\|[date\\|https://www.hl7.org/fhir/search.html#date]\\|\*SHALL\*\\|Accesses the last updated date of a FormularyItem\\|{{GET [base]/Basic?\_lastUpdated=[date]}}\\|  \\|[code\\|https://build.fhir.org/ig/HL7/davinci-pdex-formulary/SearchParameter-Basic-code.html]\\|[token\\|https://www.hl7.org/fhir/search.html#token]\\|\*SHALL\*\\|Accesses the Code of a Basis resource to find a FormularyItem\\|{{GET [base]/Basic?code=formulary-item}}\\|  \\|[subject\\|https://build.fhir.org/ig/HL7/davinci-pdex-formulary/SearchParameter-Basic-subject.html]\\|[reference\\|https://www.hl7.org/fhir/search.html#reference]\\|\*SHALL\*\\|Accesses the subject FormularyDrug (MedicationKnowledge) reference of a FormularyItem\\|{{GET [base]/Basic?subject=[reference]}}\\|  \\|[status\\|https://build.fhir.org/ig/HL7/davinci-pdex-formulary/SearchParameter-Basic-status.html]\\|[token\\|https://www.hl7.org/fhir/search.html#token]\\|\*SHALL\*\\|Accesses the status of a FormularyItem\\|{{GET [base]/Basic?status=[code]}}\\|  \\|[period\\|https://build.fhir.org/ig/HL7/davinci-pdex-formulary/SearchParameter-Basic-period.html]\\|[date\\|https://www.hl7.org/fhir/search.html#date]\\|\*SHALL\*\\|Accesses the active period of a FormularyItem\\|{{GET [base]/Basic?period=[date]}}\\|  \\|[formulary\\|https://build.fhir.org/ig/HL7/davinci-pdex-formulary/SearchParameter-Basic-formulary.html]\\|[reference\\|https://www.hl7.org/fhir/search.html#reference]\\|\*SHALL\*\\|Accesses the formulary reference of a FormularyItem\\|{{GET [base]/Basic?formulary=[reference]}}\\|  \\|[pharmacy-type\\|https://build.fhir.org/ig/HL7/davinci-pdex-formulary/SearchParameter-Basic-pharmacy-type.html]\\|[token\\|https://www.hl7.org/fhir/search.html#token]\\|\*SHALL\*\\|Accesses the Pharmacy Network Type of a FormularyItem\\|{{GET [base]/Basic?pharmacy-type=[system]\\\\|[code]}}\\|  \\|[drug-tier\\|https://build.fhir.org/ig/HL7/davinci-pdex-formulary/SearchParameter-Basic-drug-tier.html]\\|[token\\|https://www.hl7.org/fhir/search.html#token]\\|\*SHALL\*\\|Accesses the Drug Tier of a FormularyItem\\|{{GET [base]/Basic?drug-tier=[system]\\\\|[code]}}\\|       h4. FormularyDrug (MedicationKnowledge)  \\|\\|Parameter\\|\\|Type\\|\\|Conf.\\|\\|Description\\|\\|Example\\|\\|  \\|[\_id\\|http://hl7.org/fhir/R4/search.html]\\|[token\\|https://www.hl7.org/fhir/search.html#token]\\|\*SHALL\*\\|FHIR resource id of a FormularyDrug\\|{{GET [base]/MedicationKnowledge?\_id=[id]}}\\|  \\|[\_lastUpdated\\|https://build.fhir.org/ig/HL7/davinci-pdex-formulary/SearchParameter-MedicationKnowledge-lastupdated.html]\\|[date\\|https://www.hl7.org/fhir/search.html#date]\\|\*SHALL\*\\|Accesses the last updated date of a FormularyItem\\|{{GET [base]/MedicationKnowledge?\_lastUpdated=[date]}}\\|  \\|[status\\|https://build.fhir.org/ig/HL7/davinci-pdex-formulary/SearchParameter-MedicationKnowledge-status.html]\\|[token\\|https://www.hl7.org/fhir/search.html#token]\\|\*SHALL\*\\|Accesses the status of a FormularyDrug\\|{{GET [base]/MedicationKnowledge?status=[code]}}\\|  \\|[code\\|https://build.fhir.org/ig/HL7/davinci-pdex-formulary/SearchParameter-MedicationKnowledge-code.html]\\|[token\\|https://www.hl7.org/fhir/search.html#token]\\|\*SHALL\*\\|Accesses the status of a FormularyDrug\\|{{GET [base]/MedicationKnowledge?code=[system]\\\\|[code]}}\\|  \\|[drug-name\\|https://build.fhir.org/ig/HL7/davinci-pdex-formulary/SearchParameter-MedicationKnowledge-drug-name.html]\\|[string\\|https://www.hl7.org/fhir/search.html#string]\\|\*SHALL\*\\|Accesses the Drug Name of a FormularyDrug\\|{{GET [base]/MedicationKnowledge?drug-name=[string]}}\\|  \\|[doseform\\|https://build.fhir.org/ig/HL7/davinci-pdex-formulary/SearchParameter-MedicationKnowledge-doseform.html]\\|[token\\|https://www.hl7.org/fhir/search.html#token]\\|\*SHOULD\*\\|Accesses the dose form of a FormularyDrug\\|{{GET [base]/MedicationKnowledge?doseform=[system\\\\|code]}}\\|      |
| [FHIR-33182](https://jira.hl7.org/browse/FHIR-33182) |  | Create a FormularyItem profile on the Basic resource with:   \* subject pointing to the FormularyDrug (MedicationKnowledge)   \* an extension pointing to a single Formulary InsurancePlan   \* necessary FormularyDrug extensions moved (and removed from FormularyDrug) to FormularyItem |
| [FHIR-33181](https://jira.hl7.org/browse/FHIR-33181) |  | Change the use of CoveragePlan as a profile on List to use two profiles on InsurancePlan, one for the top level subscribable Insurance plan and one representing the formulary |
| [FHIR-31673](https://jira.hl7.org/browse/FHIR-31673) | [http://hl7.org/fhir/us/davinci-drug-formulary/StructureDefinition-usdf-EmailPlanContact-extension.html](http://hl7.org/fhir/us/davinci-drug-formulary/StructureDefinition-usdf-EmailPlanContact-extension.html) | CoveragePlan profile on List, change InsurancePlan, with contact that can be email, url, and other valid telecom systems. |
| [FHIR-31572](https://jira.hl7.org/browse/FHIR-31572) |  | Identifiers that need to be used for referencing between resources need to be required. The IG is being restructured to support a different set of resources. These resources are linked using the reference types whose elements are required.   \* Payer Insurance Plan extension for DrugPlanReference 1..1 MS   \* FormularyItem.subject reference for FormularyDrug 1..1 MS   \* FormularyItem extension for DrugPlanReference 1..1 MS |
| [FHIR-31349](https://jira.hl7.org/browse/FHIR-31349) |  | Add code to both [http://hl7.org/fhir/us/davinci-drug-formulary/ValueSet/CopayOptionVS] and http://hl7.org/fhir/us/davinci-drug-formulary/ValueSet/CoinsuranceOptionVS    Defined as     \*code:\* deductible-waived  \*display:\* Deductible Waived  \*copay definition:\* The consumer pays the copay with deductible requirement waived.    \*coinsurance definition:\* The consumer pays the coinsurance with deductible requirement waived. |
| [FHIR-31038](https://jira.hl7.org/browse/FHIR-31038) |  | Change CoveragePlan profile on List into two profiles on InsurancePlan, one for a top level subscribable plan and the other for formulary profile on InsurancePlan.    Add Search Parameters:   \* InsurancePlan identifier to enable query by business identifier   \* InsurancePlan type to query on insurance plan type   \* Formulary reference in coverage to query on Insurance plans that include a particular formulary    All Coverage plans can be searched for or can be narrowed down to the payer insurance plan or formulary using the codesystem. |
| [FHIR-30923](https://jira.hl7.org/browse/FHIR-30923) |  | Address through a restructuring of the profiles included in the IG.   \* Change CoveragePlan profile on List to InsuracePlan   \* Add FormularyItem Profile on Basic with extensions moved from FormularyDrug profile   \* Enable linking multiple FormularyDrugs with multiple InsurancePlans through multiple FormularyItems pointing to a formulary InsurancePlan. |
| [FHIR-29964](https://jira.hl7.org/browse/FHIR-29964) |  | Add extensions:   \* PriorAuthorizationNewStartsOnly boolean 0..1 MS   \* StepTherapyNewStartsOnly boolean 0..1 MS   \* QuantityLimitDetail complex MS   \*\* Description   \*\* Rolling   \*\* MaximumDaily   \*\* DaysSupply      |
